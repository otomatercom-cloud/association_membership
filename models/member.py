from odoo import _, api, fields, models

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
    mobile = fields.Char(related='partner_id.mobile', string='Mobile Number (Call)', store=True, readonly=False)
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

    user_id = fields.Many2one('res.users', string='User Account', copy=False)
    application_id = fields.Many2one('association.membership.application', string='Source Application', copy=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _member_number_uniq = models.Constraint(
        'unique(member_number, company_id)',
        'Member ID must be unique.',
    )

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
