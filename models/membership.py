from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AssociationMembership(models.Model):
    _name = 'association.membership'
    _description = 'Association Membership'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'

    name = fields.Char(
        string='Membership Number', required=True, copy=False,
        readonly=True, default=lambda self: _('New'),
    )
    member_id = fields.Many2one(
        'association.member', string='Member', required=True,
        index=True, tracking=True, ondelete='cascade',
    )
    membership_type_id = fields.Many2one(
        'association.membership.type', string='Membership Type',
        required=True, tracking=True,
    )

    start_date = fields.Date(string='Start Date', tracking=True)
    expiry_date = fields.Date(string='Expiry Date', tracking=True)

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    fee = fields.Monetary(string='Fee', currency_field='currency_id')
    renewal_fee = fields.Monetary(string='Renewal Fee', currency_field='currency_id')

    payment_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('paid', 'Paid'),
        ],
        string='Payment Status', default='pending', tracking=True,
    )

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('suspended', 'Suspended'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', required=True, tracking=True,
    )

    previous_membership_id = fields.Many2one('association.membership', string='Previous Membership', copy=False, index=True)
    renewal_membership_id = fields.Many2one('association.membership', string='Renewal Membership', copy=False, readonly=True)

    activation_date = fields.Datetime(string='Activation Date', readonly=True, copy=False)
    cancellation_date = fields.Datetime(string='Cancellation Date', readonly=True, copy=False)
    cancellation_reason = fields.Text(string='Cancellation Reason')

    application_id = fields.Many2one('association.membership.application', string='Source Application', copy=False, index=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Payment (Phase 3)
    payment_ids = fields.One2many('association.membership.payment', 'membership_id', string='Payments')
    payment_count = fields.Integer(string='Payment Count', compute='_compute_payment_count')

    _membership_number_uniq = models.Constraint(
        'unique(name, company_id)',
        'Membership Number must be unique.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('association.membership') or _('New')
            if not vals.get('start_date'):
                vals['start_date'] = fields.Date.context_today(self)
            if not vals.get('expiry_date') and vals.get('membership_type_id') and vals.get('start_date'):
                mtype = self.env['association.membership.type'].browse(vals['membership_type_id'])
                vals['expiry_date'] = mtype.get_expiry_date(fields.Date.from_string(vals['start_date']))
        return super().create(vals_list)

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)

    def action_view_payments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'association_membership.action_association_membership_payment')
        action['domain'] = [('membership_id', '=', self.id)]
        action['context'] = {
            'default_membership_id': self.id,
            'default_payment_purpose': 'renewal',
        }
        return action

    def action_activate(self):
        for rec in self:
            if rec.state not in ('draft', 'suspended'):
                raise UserError(_('Only draft or suspended memberships can be activated.'))
            if not rec.expiry_date and rec.membership_type_id:
                rec.expiry_date = rec.membership_type_id.get_expiry_date(rec.start_date or fields.Date.context_today(rec))
            rec.write({
                'state': 'active',
                'activation_date': fields.Datetime.now(),
            })
            rec.member_id.status = 'active'
            if rec.member_id.digital_card_enabled:
                rec.member_id._ensure_card_token()

    def action_suspend(self):
        for rec in self:
            if rec.state != 'active':
                raise UserError(_('Only active memberships can be suspended.'))
            rec.state = 'suspended'

    def action_cancel(self, reason=None):
        for rec in self:
            rec.write({
                'state': 'cancelled',
                'cancellation_date': fields.Datetime.now(),
                'cancellation_reason': reason or rec.cancellation_reason,
            })

    def action_expire(self):
        for rec in self:
            if rec.state == 'active':
                rec.state = 'expired'
                if rec.member_id.current_membership_id == rec:
                    rec.member_id.status = 'expired'

    def action_renew(self):
        """Create a new membership record continuing this one.

        A brand new association.membership record is created (never
        overwriting this one) so the member's membership history is
        preserved, per spec section 15.
        """
        self.ensure_one()
        if self.state not in ('active', 'expired'):
            raise UserError(_('Only active or expired memberships can be renewed.'))
        new_start = self.expiry_date + relativedelta(days=1) if self.expiry_date else fields.Date.context_today(self)
        renewal_amount = self.membership_type_id.renewal_fee or self.membership_type_id.membership_fee
        new_membership = self.create({
            'member_id': self.member_id.id,
            'membership_type_id': self.membership_type_id.id,
            'fee': renewal_amount,
            'renewal_fee': self.membership_type_id.renewal_fee,
            'start_date': new_start,
            'previous_membership_id': self.id,
            'payment_status': 'pending',
        })
        self.renewal_membership_id = new_membership.id
        if renewal_amount > 0:
            mtype = self.membership_type_id
            tax_amount = round(renewal_amount * (mtype.tax_percentage or 0.0) / 100.0, 2) if mtype.tax_percentage else 0.0
            self.env['association.membership.payment'].create({
                'membership_id': new_membership.id,
                'payment_purpose': 'renewal',
                'currency_id': mtype.currency_id.id,
                'amount': renewal_amount,
                'tax_amount': tax_amount,
                'payment_method': 'cash',
                'state': 'draft',
            })
        else:
            new_membership.payment_status = 'paid'
        return new_membership
