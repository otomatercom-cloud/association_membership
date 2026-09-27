from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PAYMENT_PURPOSES = [
    ('joining', 'Joining Fee'),
    ('membership', 'Membership Fee'),
    ('renewal', 'Renewal Fee'),
    ('other', 'Other'),
]

PAYMENT_METHODS = [
    ('cash', 'Cash'),
    ('bank_transfer', 'Bank Transfer'),
    ('cheque', 'Cheque'),
    ('online', 'Online Payment'),
    ('other', 'Other'),
]

# Manual recording is the only working path today. The gateway_* fields
# below exist so a future phase can wire up Razorpay/Stripe without a
# schema change: an online checkout would create a 'pending' payment,
# populate gateway_order_id, then a webhook/return handler would set
# gateway_transaction_id + gateway_response and call action_confirm().
GATEWAY_PROVIDERS = [
    ('none', 'Manual / Offline'),
    ('razorpay', 'Razorpay'),
    ('stripe', 'Stripe'),
]


class AssociationMembershipPayment(models.Model):
    _name = 'association.membership.payment'
    _description = 'Association Membership Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'payment_date desc, id desc'

    name = fields.Char(
        string='Payment Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New'),
    )

    application_id = fields.Many2one(
        'association.membership.application', string='Application',
        ondelete='cascade', index=True, tracking=True,
    )
    membership_id = fields.Many2one(
        'association.membership', string='Membership',
        ondelete='set null', index=True, tracking=True,
    )
    member_id = fields.Many2one(
        'association.member', string='Member',
        compute='_compute_member_id', store=True, index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
        compute='_compute_partner_id', store=True,
    )

    payment_purpose = fields.Selection(
        PAYMENT_PURPOSES, string='Purpose', required=True,
        default='membership', tracking=True,
    )

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id, required=True,
    )
    amount = fields.Monetary(string='Amount', currency_field='currency_id', required=True, tracking=True)
    tax_amount = fields.Monetary(string='Tax Amount', currency_field='currency_id', default=0.0)
    total_amount = fields.Monetary(
        string='Total Amount', currency_field='currency_id',
        compute='_compute_total_amount', store=True,
    )

    payment_method = fields.Selection(
        PAYMENT_METHODS, string='Payment Method', required=True,
        default='cash', tracking=True,
    )
    reference_number = fields.Char(string='Reference / Cheque / Transaction No.')
    payment_date = fields.Date(string='Payment Date', default=fields.Date.context_today, required=True, tracking=True)
    notes = fields.Text(string='Notes')

    # --- Gateway-ready fields (unused by the manual flow; see note above) ---
    gateway_provider = fields.Selection(GATEWAY_PROVIDERS, string='Gateway', default='none', required=True, tracking=True)
    gateway_order_id = fields.Char(string='Gateway Order ID', copy=False)
    gateway_transaction_id = fields.Char(string='Gateway Transaction ID', copy=False)
    gateway_response = fields.Text(string='Gateway Raw Response', copy=False)
    gateway_verified = fields.Boolean(string='Signature Verified', default=False, copy=False)

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('pending', 'Pending Confirmation'),
            ('confirmed', 'Confirmed'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
            ('refunded', 'Refunded'),
        ],
        string='Status', default='draft', required=True, tracking=True,
    )

    confirmed_by = fields.Many2one('res.users', string='Confirmed By', readonly=True, copy=False)
    confirmed_date = fields.Datetime(string='Confirmed On', readonly=True, copy=False)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _payment_number_uniq = models.Constraint(
        'unique(name, company_id)',
        'Payment Reference must be unique.',
    )

    @api.depends('amount', 'tax_amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = (rec.amount or 0.0) + (rec.tax_amount or 0.0)

    @api.depends('application_id.member_id', 'membership_id.member_id')
    def _compute_member_id(self):
        for rec in self:
            rec.member_id = rec.membership_id.member_id or rec.application_id.member_id or False

    @api.depends('member_id.partner_id', 'application_id.partner_id')
    def _compute_partner_id(self):
        for rec in self:
            rec.partner_id = rec.member_id.partner_id or rec.application_id.partner_id or False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'association.membership.payment') or _('New')
        return super().create(vals_list)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('Payment amount must be greater than zero.'))

    def action_confirm(self):
        for rec in self:
            if rec.state not in ('draft', 'pending'):
                raise UserError(_('Only draft or pending payments can be confirmed.'))
            rec.write({
                'state': 'confirmed',
                'confirmed_by': self.env.user.id,
                'confirmed_date': fields.Datetime.now(),
            })
            rec._on_confirmed()

    def _on_confirmed(self):
        """Propagate a confirmed payment back to the application/membership
        it belongs to, so the two workflows stay in sync automatically.
        """
        self.ensure_one()
        if self.application_id and self.application_id.state == 'payment_pending':
            self.application_id.action_mark_payment_received()
        if self.membership_id and self.membership_id.payment_status != 'paid':
            self.membership_id.payment_status = 'paid'

    def action_mark_failed(self):
        for rec in self:
            if rec.state not in ('draft', 'pending'):
                raise UserError(_('Only draft or pending payments can be marked as failed.'))
            rec.state = 'failed'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('A confirmed payment cannot be cancelled directly. Refund it instead.'))
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('A confirmed payment cannot be reset to draft. Refund it instead.'))
            rec.state = 'draft'

    def action_refund(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Only confirmed payments can be refunded.'))
            rec.state = 'refunded'
