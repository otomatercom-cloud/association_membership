import base64
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

CARD_STATUS = [
    ('active', 'Active'),
    ('expired', 'Expired'),
    ('suspended', 'Suspended'),
    ('cancelled', 'Cancelled'),
    ('inactive', 'Not Yet Active'),
]

GENDER_SELECTION = [
    ('male', 'Male'),
    ('female', 'Female'),
    ('other', 'Other'),
]

ID_PROOF_TYPES = [
    ('aadhaar', 'Aadhaar Card'),
    ('pan', 'PAN Card'),
    ('passport', 'Passport'),
    ('voter_id', 'Voter ID'),
    ('driving_license', 'Driving License'),
    ('other', 'Other'),
]


class AssociationMember(models.Model):
    _name = 'association.member'
    _description = 'Association Member'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'member_number'

    member_number = fields.Char(
        string='Member ID', required=True, copy=False,
        readonly=True, default=lambda self: _('New'),
    )
    partner_id = fields.Many2one(
        'res.partner', string='Contact', required=True,
        tracking=True, ondelete='restrict', index=True,
    )

    # Related to res.partner so contact data is not duplicated - editable
    # directly from the Member form (standard Odoo related+store pattern).
    name = fields.Char(related='partner_id.name', string='Full Name', store=True, readonly=False)
    email = fields.Char(related='partner_id.email', string='Email', store=True, readonly=False)
    # NOT related to partner_id: this Odoo 19 instance's res.partner has no
    # 'mobile' field (only 'phone') - confirmed by a real install error.
    # Stored independently here, same pattern as 'whatsapp' below.
    mobile = fields.Char(string='Mobile Number (Call)')
    whatsapp = fields.Char(string='Mobile Number (WhatsApp)')
    photo = fields.Image(related='partner_id.image_1920', string='Passport Size Photo', store=True, readonly=False)
    street = fields.Char(related='partner_id.street', string='Address in India', store=True, readonly=False)
    city = fields.Char(related='partner_id.city', string='Place', store=True, readonly=False)
    state_id = fields.Many2one(related='partner_id.state_id', string='State', store=True, readonly=False)
    country_id = fields.Many2one(related='partner_id.country_id', string='Country', store=True, readonly=False)
    zip = fields.Char(related='partner_id.zip', string='PIN Code', store=True, readonly=False)

    date_of_birth = fields.Date(string='Date of Birth')
    gender = fields.Selection(GENDER_SELECTION, string='Gender')
    blood_group = fields.Selection(
        [
            ('a+', 'A+'), ('a-', 'A-'), ('b+', 'B+'), ('b-', 'B-'),
            ('ab+', 'AB+'), ('ab-', 'AB-'), ('o+', 'O+'), ('o-', 'O-'),
        ],
        string='Blood Group',
    )
    job = fields.Char(string='Job')

    occupation = fields.Char(string='Occupation')
    company_name = fields.Char(string='Company / Organization')
    designation = fields.Char(string='Designation')

    # KSA (Saudi Arabia) residency details
    iqama_number = fields.Char(string='Iqama Number', tracking=True)
    passport_number = fields.Char(string='Passport Number', tracking=True)
    ksa_province = fields.Char(string='KSA Province')
    ksa_area = fields.Char(string='KSA Area')

    id_proof_type = fields.Selection(ID_PROOF_TYPES, string='ID Proof Type')
    id_proof_number = fields.Char(string='ID Proof Number')
    id_proof_document = fields.Binary(string='ID Proof Document', attachment=True)
    id_proof_document_name = fields.Char(string='ID Proof Filename')

    membership_type_id = fields.Many2one(
        'association.membership.type', string='Current Membership Type', tracking=True,
    )
    digital_card_enabled = fields.Boolean(
        related='membership_type_id.digital_card_enabled', string='Digital Card Enabled', store=True,
    )
    joining_date = fields.Date(string='Joining Date', default=fields.Date.context_today)

    membership_ids = fields.One2many('association.membership', 'member_id', string='Membership History')
    current_membership_id = fields.Many2one(
        'association.membership', string='Current Membership',
        compute='_compute_current_membership', store=True,
    )
    membership_start_date = fields.Date(related='current_membership_id.start_date', string='Membership Start Date', store=True)
    membership_expiry_date = fields.Date(related='current_membership_id.expiry_date', string='Membership Expiry Date', store=True)

    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('suspended', 'Suspended'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', required=True, tracking=True,
    )

    user_id = fields.Many2one('res.users', string='Portal User Account', copy=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_has_portal_access')
    application_id = fields.Many2one('association.membership.application', string='Source Application', copy=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    # Payment (Phase 3, surfaced on the member for portal/backend visibility)
    payment_ids = fields.One2many(
        'association.membership.payment', 'member_id', string='Payments', readonly=True,
    )
    payment_count = fields.Integer(string='Payment Count', compute='_compute_payment_count')

    # Digital Membership Card (Phase 5)
    card_token = fields.Char(
        string='Card Token', copy=False, readonly=True, index=True,
        help='Unguessable token used in the public verification URL printed/encoded on the card.',
    )
    card_issued_date = fields.Date(string='Card Issued On', readonly=True, copy=False)
    card_verify_url = fields.Char(string='Verification URL', compute='_compute_card_verify_url')
    card_status = fields.Selection(CARD_STATUS, string='Card Status', compute='_compute_card_status')

    _member_number_uniq = models.Constraint(
        'unique(member_number, company_id)',
        'Member ID must be unique.',
    )
    _card_token_uniq = models.Constraint(
        'unique(card_token)',
        'Card Token must be unique.',
    )

    @api.depends('user_id')
    def _compute_has_portal_access(self):
        for rec in self:
            rec.has_portal_access = bool(rec.user_id)

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)

    def action_view_payments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'association_membership.action_association_membership_payment')
        action['domain'] = [('member_id', '=', self.id)]
        return action

    @api.depends('card_token')
    def _compute_card_verify_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for rec in self:
            rec.card_verify_url = '%s/membership/verify/%s' % (base_url, rec.card_token) if rec.card_token else False

    @api.depends('status', 'current_membership_id.state', 'current_membership_id.expiry_date')
    def _compute_card_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.status == 'cancelled':
                rec.card_status = 'cancelled'
            elif rec.status == 'suspended':
                rec.card_status = 'suspended'
            elif rec.current_membership_id and rec.current_membership_id.expiry_date and rec.current_membership_id.expiry_date < today:
                rec.card_status = 'expired'
            elif rec.status == 'active' and rec.current_membership_id and rec.current_membership_id.state == 'active':
                rec.card_status = 'active'
            else:
                rec.card_status = 'inactive'

    def _ensure_card_token(self):
        for rec in self:
            vals = {}
            if not rec.card_token:
                vals['card_token'] = secrets.token_urlsafe(24)
            if not rec.card_issued_date:
                vals['card_issued_date'] = fields.Date.context_today(rec)
            if vals:
                rec.write(vals)

    def action_print_card(self):
        self.ensure_one()
        if not self.digital_card_enabled:
            raise UserError(_('Digital card is not enabled for this membership type.'))
        if self.status not in ('active', 'suspended', 'expired'):
            raise UserError(_('A digital card can only be issued once the member has an active membership.'))
        self._ensure_card_token()
        return self.env.ref('association_membership.action_report_membership_card').report_action(self)

    def action_email_card(self):
        """Render the digital card as a PDF and email it to the member's
        own contact as an attachment. Reuses the exact same report the
        Print/portal-download buttons use, so the emailed PDF is always
        identical to what staff would see if they printed it themselves.
        """
        self.ensure_one()
        if not self.digital_card_enabled:
            raise UserError(_('Digital card is not enabled for this membership type.'))
        if self.status not in ('active', 'suspended', 'expired'):
            raise UserError(_('A digital card can only be issued once the member has an active membership.'))
        if not self.partner_id.email:
            raise UserError(_('This member\'s contact has no email address on file.'))
        self._ensure_card_token()

        report = self.env.ref('association_membership.action_report_membership_card')
        pdf_content, _report_format = report.sudo()._render_qweb_pdf(report, res_ids=[self.id])
        attachment = self.env['ir.attachment'].create({
            'name': 'Membership Card - %s.pdf' % (self.member_number or self.name),
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        body_html = _(
            '<p>Dear %(name)s,</p>'
            '<p>Please find attached your Digital Membership Card (%(member_number)s).</p>'
            '<p>You can also view it anytime, along with a QR verification code, from your member portal.</p>'
        ) % {'name': self.name, 'member_number': self.member_number}
        self.env['mail.mail'].sudo().create({
            'subject': _('Your Digital Membership Card - %s') % self.member_number,
            'body_html': body_html,
            'email_to': self.partner_id.email,
            'attachment_ids': [(6, 0, [attachment.id])],
            'auto_delete': False,
        }).send()
        self.message_post(body=_('Digital membership card emailed to %s.') % self.partner_id.email)
        return True

    @api.depends('membership_ids.state', 'membership_ids.expiry_date')
    def _compute_current_membership(self):
        for rec in self:
            active_memberships = rec.membership_ids.filtered(lambda m: m.state == 'active')
            rec.current_membership_id = active_memberships.sorted('expiry_date', reverse=True)[0] if active_memberships else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('member_number', _('New')) == _('New'):
                vals['member_number'] = self.env['ir.sequence'].sudo().next_by_code('association.member') or _('New')
        return super().create(vals_list)

    def action_suspend(self):
        for rec in self:
            rec.status = 'suspended'
            rec.membership_ids.filtered(lambda m: m.state == 'active').action_suspend()

    def action_reactivate(self):
        for rec in self:
            rec.status = 'active'
            rec.membership_ids.filtered(lambda m: m.state == 'suspended').action_activate()

    def action_cancel(self):
        for rec in self:
            rec.status = 'cancelled'
            rec.membership_ids.filtered(lambda m: m.state in ('active', 'suspended')).action_cancel(
                reason=_('Member cancelled.'))

    def action_grant_portal_access(self):
        """Create a portal user for this member's contact and email them an
        invite to set their own password, so they can log in to /my/membership.
        Idempotent: a member who already has a user account is left alone.
        """
        self.ensure_one()
        if self.user_id:
            raise UserError(_('%s already has a portal user account.') % self.name)
        if not self.partner_id.email:
            raise UserError(_('Add an email address to the contact before granting portal access.'))
        existing_user = self.env['res.users'].sudo().search(
            [('login', '=', self.partner_id.email)], limit=1)
        if existing_user:
            portal_group = self.env.ref('base.group_portal')
            if portal_group not in existing_user.group_ids:
                existing_user.sudo().write({'group_ids': [(4, portal_group.id)]})
            if existing_user.partner_id != self.partner_id:
                raise UserError(_(
                    'A user already exists with the login %s but is linked to a different contact. '
                    'Please resolve this manually from Settings > Users.'
                ) % self.partner_id.email)
            self.user_id = existing_user.id
            return True
        portal_group = self.env.ref('base.group_portal')
        user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': self.partner_id.name,
            'login': self.partner_id.email,
            'email': self.partner_id.email,
            'partner_id': self.partner_id.id,
            'group_ids': [(6, 0, [portal_group.id])],
        })
        user.sudo().action_reset_password()
        self.user_id = user.id
        return True
