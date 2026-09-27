import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

ID_PROOF_TYPES = [
    ('aadhaar', 'Aadhaar Card'),
    ('pan', 'PAN Card'),
    ('passport', 'Passport'),
    ('voter_id', 'Voter ID'),
    ('driving_license', 'Driving License'),
    ('other', 'Other'),
]

GENDER_SELECTION = [
    ('male', 'Male'),
    ('female', 'Female'),
    ('other', 'Other'),
]


class AssociationMembershipApplication(models.Model):
    _name = 'association.membership.application'
    _description = 'Association Membership Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'application_date desc, id desc'

    name = fields.Char(
        string='Application Number', required=True, copy=False,
        readonly=True, default=lambda self: _('New'),
    )

    # Personal Information
    applicant_name = fields.Char(string='Full Name', required=True, tracking=True)
    photo = fields.Image(string='Passport Size Photo', max_width=1024, max_height=1024)
    date_of_birth = fields.Date(string='Date of Birth')
    gender = fields.Selection(GENDER_SELECTION, string='Gender')
    blood_group = fields.Selection(
        [
            ('a+', 'A+'), ('a-', 'A-'), ('b+', 'B+'), ('b-', 'B-'),
            ('ab+', 'AB+'), ('ab-', 'AB-'), ('o+', 'O+'), ('o-', 'O-'),
        ],
        string='Blood Group',
    )
    mobile = fields.Char(string='Mobile Number (Call)', required=True, tracking=True)
    whatsapp = fields.Char(string='Mobile Number (WhatsApp)')
    email = fields.Char(string='Email', required=True, tracking=True)
    nationality_id = fields.Many2one('res.country', string='Nationality')
    job = fields.Char(string='Job')

    # KSA (Saudi Arabia) residency details
    iqama_number = fields.Char(string='Iqama Number', tracking=True)
    passport_number = fields.Char(string='Passport Number', tracking=True)
    ksa_province = fields.Char(string='KSA Province')
    ksa_area = fields.Char(string='KSA Area')

    # Address in India
    house_address = fields.Char(string='Address in India')
    street = fields.Char(string='Street')
    place = fields.Char(string='Place')
    district = fields.Char(string='District')
    state_id = fields.Many2one('res.country.state', string='State')
    country_id = fields.Many2one('res.country', string='Country', default=lambda self: self.env.ref('base.in', raise_if_not_found=False))
    pin_code = fields.Char(string='PIN Code')

    # Professional Information
    occupation = fields.Char(string='Occupation')
    company_name = fields.Char(string='Company / Organization')
    designation = fields.Char(string='Designation')
    work_address = fields.Text(string='Work Address')

    # Identity Documents (upload copies, distinct from the Iqama/Passport
    # number fields above which are for quick reference/search)
    id_proof_type = fields.Selection(ID_PROOF_TYPES, string='ID Proof Type')
    id_proof_number = fields.Char(string='ID Proof Number')
    id_proof_document = fields.Binary(string='ID Proof Document', attachment=True)
    id_proof_document_name = fields.Char(string='ID Proof Filename')

    # Emergency Contact
    emergency_contact_name = fields.Char(string='Emergency Contact Name')
    emergency_contact_relationship = fields.Char(string='Emergency Contact Relationship')
    emergency_contact_mobile = fields.Char(string='Emergency Contact Mobile')

    # Membership
    membership_type_id = fields.Many2one(
        'association.membership.type', string='Membership Type',
        required=True, tracking=True,
    )
    membership_category = fields.Char(string='Membership Category')
    referral_member_id = fields.Many2one(
        'association.member', string='Referral / Existing Member',
        help='Linked by staff during verification, once the referral is confirmed.',
    )
    referral_reference = fields.Char(
        string='Referral Name / Member ID',
        help='Free-text name or Member ID entered by the applicant on the public form.',
    )
    additional_info = fields.Text(string='Additional Information')

    # Application meta
    application_date = fields.Date(string='Application Date', required=True, default=fields.Date.context_today)
    verification_notes = fields.Text(string='Verification Notes')
    rejection_reason = fields.Text(string='Rejection Reason')
    payment_status = fields.Selection(
        [
            ('not_required', 'Not Required'),
            ('pending', 'Pending'),
            ('paid', 'Paid'),
        ],
        string='Payment Status', default='not_required', tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('under_verification', 'Under Verification'),
            ('payment_pending', 'Payment Pending'),
            ('payment_received', 'Payment Received'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', required=True, tracking=True,
    )

    member_id = fields.Many2one('association.member', string='Created Member', readonly=True, copy=False)
    membership_id = fields.Many2one('association.membership', string='Created Membership', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Contact', copy=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Payment (Phase 3)
    currency_id = fields.Many2one(
        related='membership_type_id.currency_id', string='Currency', store=True, readonly=True,
    )
    payment_ids = fields.One2many(
        'association.membership.payment', 'application_id', string='Payments',
    )
    payment_count = fields.Integer(string='Payment Count', compute='_compute_payment_totals')
    amount_due = fields.Monetary(string='Amount Due', currency_field='currency_id', compute='_compute_payment_totals')
    amount_paid = fields.Monetary(string='Amount Paid', currency_field='currency_id', compute='_compute_payment_totals')
    balance_due = fields.Monetary(string='Balance Due', currency_field='currency_id', compute='_compute_payment_totals')

    _application_number_uniq = models.Constraint(
        'unique(name, company_id)',
        'Application Number must be unique.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'association.membership.application') or _('New')
        return super().create(vals_list)

    @api.constrains('email')
    def _check_email(self):
        for rec in self:
            if rec.email and not EMAIL_RE.match(rec.email):
                raise ValidationError(_('Please enter a valid email address for %s.') % rec.applicant_name)

    @api.constrains('mobile', 'whatsapp', 'emergency_contact_mobile')
    def _check_mobile_numbers(self):
        for rec in self:
            for fname, label in (
                ('mobile', 'Mobile Number (Call)'),
                ('whatsapp', 'Mobile Number (WhatsApp)'),
                ('emergency_contact_mobile', 'Emergency Contact Mobile'),
            ):
                value = rec[fname]
                if value:
                    digits = ''.join(ch for ch in value if ch.isdigit())
                    if len(digits) < 10:
                        raise ValidationError(_('%s must contain at least 10 digits.') % label)

    @api.constrains('pin_code')
    def _check_pin_code(self):
        for rec in self:
            if rec.pin_code and not rec.pin_code.strip().isdigit():
                raise ValidationError(_('PIN Code must contain digits only.'))

    @api.depends(
        'payment_ids.state', 'payment_ids.total_amount',
        'membership_type_id.membership_fee', 'membership_type_id.joining_fee',
    )
    def _compute_payment_totals(self):
        for rec in self:
            due = (rec.membership_type_id.membership_fee or 0.0) + (rec.membership_type_id.joining_fee or 0.0)
            confirmed = rec.payment_ids.filtered(lambda p: p.state == 'confirmed')
            paid = sum(confirmed.mapped('total_amount'))
            rec.payment_count = len(rec.payment_ids)
            rec.amount_due = due
            rec.amount_paid = paid
            rec.balance_due = max(due - paid, 0.0)

    @api.model
    def check_duplicate(self, email=None, mobile=None, id_proof_number=None,
                         iqama_number=None, passport_number=None):
        """Return an existing application matching email, mobile, ID proof,
        Iqama or Passport number.

        Used by the public website form (Phase 2) to warn the visitor of an
        existing application/member before they submit a duplicate one.
        """
        domain = []
        if email:
            domain.append(('email', '=', email))
        if mobile:
            domain.append(('mobile', '=', mobile))
        if id_proof_number:
            domain.append(('id_proof_number', '=', id_proof_number))
        if iqama_number:
            domain.append(('iqama_number', '=', iqama_number))
        if passport_number:
            domain.append(('passport_number', '=', passport_number))
        if not domain:
            return self.browse()
        or_domain = ['|'] * (len(domain) - 1) + domain
        return self.search(or_domain, limit=1)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft applications can be submitted.'))
            rec.state = 'submitted'

    def action_start_verification(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted applications can move to verification.'))
            rec.state = 'under_verification'

    def action_request_correction(self):
        for rec in self:
            if rec.state != 'under_verification':
                raise UserError(_('Only applications under verification can be sent back for correction.'))
            if not rec.verification_notes:
                raise UserError(_('Please add verification notes explaining what needs to be corrected.'))
            rec.state = 'draft'

    def action_send_for_payment(self):
        for rec in self:
            if rec.state != 'under_verification':
                raise UserError(_('Only verified applications can be sent for payment.'))
            rec.state = 'payment_pending'
            rec.payment_status = 'pending'
            if rec.amount_due > 0:
                rec._create_payment_record()

    def _create_payment_record(self):
        """Create (or return the existing) draft/pending payment for this
        application's amount due. Called automatically when an application
        is sent for payment; also callable again as a safety net if that
        payment was cancelled/failed and a fresh one is needed.
        """
        self.ensure_one()
        open_payment = self.payment_ids.filtered(lambda p: p.state in ('draft', 'pending'))
        if open_payment:
            return open_payment[0]
        mtype = self.membership_type_id
        amount = (mtype.membership_fee or 0.0) + (mtype.joining_fee or 0.0)
        tax_amount = round(amount * (mtype.tax_percentage or 0.0) / 100.0, 2) if mtype.tax_percentage else 0.0
        return self.env['association.membership.payment'].create({
            'application_id': self.id,
            'payment_purpose': 'membership',
            'currency_id': mtype.currency_id.id,
            'amount': amount,
            'tax_amount': tax_amount,
            'payment_method': 'cash',
            'state': 'draft',
        })

    def action_mark_payment_received(self):
        for rec in self:
            if rec.state != 'payment_pending':
                raise UserError(_('Only applications pending payment can be marked as paid.'))
            rec.state = 'payment_received'
            rec.payment_status = 'paid'

    def action_approve(self):
        for rec in self:
            if rec.state == 'under_verification' and rec.membership_type_id.membership_fee > 0:
                raise UserError(_(
                    'This membership type requires payment before approval. '
                    'Please send the application for payment first.'
                ))
            if rec.state not in ('payment_received', 'under_verification'):
                raise UserError(_('Only verified or paid applications can be approved.'))
            rec._create_member_and_membership()
            rec.state = 'approved'

    def action_reject(self):
        for rec in self:
            if not rec.rejection_reason:
                raise UserError(_('Please provide a rejection reason.'))
            rec.state = 'rejected'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_('An approved application cannot be cancelled directly.'))
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_view_payments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'association_membership.action_association_membership_payment')
        action['domain'] = [('application_id', '=', self.id)]
        action['context'] = {
            'default_application_id': self.id,
            'default_payment_purpose': 'membership',
        }
        return action

    def _find_or_create_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        partner = self.env['res.partner']
        if self.email:
            partner = partner.search([('email', '=', self.email)], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': self.applicant_name,
                'email': self.email,
                'phone': self.mobile,
                'street': self.house_address,
                'city': self.place,
                'state_id': self.state_id.id,
                'country_id': self.country_id.id,
                'zip': self.pin_code,
                'company_type': 'person',
                'image_1920': self.photo,
            })
        elif self.photo and not partner.image_1920:
            partner.image_1920 = self.photo
        self.partner_id = partner
        return partner

    def _create_member_and_membership(self):
        self.ensure_one()
        member = self.member_id
        if not member:
            partner = self._find_or_create_partner()
            member = self.env['association.member'].create({
                'partner_id': partner.id,
                'mobile': self.mobile,
                'whatsapp': self.whatsapp,
                'date_of_birth': self.date_of_birth,
                'gender': self.gender,
                'blood_group': self.blood_group,
                'job': self.job,
                'occupation': self.occupation,
                'company_name': self.company_name,
                'designation': self.designation,
                'iqama_number': self.iqama_number,
                'passport_number': self.passport_number,
                'ksa_province': self.ksa_province,
                'ksa_area': self.ksa_area,
                'id_proof_type': self.id_proof_type,
                'id_proof_number': self.id_proof_number,
                'id_proof_document': self.id_proof_document,
                'id_proof_document_name': self.id_proof_document_name,
                'membership_type_id': self.membership_type_id.id,
                'joining_date': fields.Date.context_today(self),
                'application_id': self.id,
            })
            self.member_id = member.id

        if not self.membership_id:
            membership = self.env['association.membership'].create({
                'member_id': member.id,
                'membership_type_id': self.membership_type_id.id,
                'fee': self.membership_type_id.membership_fee,
                'renewal_fee': self.membership_type_id.renewal_fee,
                'payment_status': self.payment_status if self.payment_status in ('pending', 'paid') else 'pending',
                'application_id': self.id,
            })
            membership.action_activate()
            self.membership_id = membership.id

        return member
