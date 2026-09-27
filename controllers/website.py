import base64
import os
import re
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

GENDER_SELECTION = [
    ('male', 'Male'),
    ('female', 'Female'),
    ('other', 'Other'),
]

BLOOD_GROUPS = [
    ('a+', 'A+'), ('a-', 'A-'), ('b+', 'B+'), ('b-', 'B-'),
    ('ab+', 'AB+'), ('ab-', 'AB-'), ('o+', 'O+'), ('o-', 'O-'),
]

ID_PROOF_TYPES = [
    ('aadhaar', 'Aadhaar Card'),
    ('pan', 'PAN Card'),
    ('passport', 'Passport'),
    ('voter_id', 'Voter ID'),
    ('driving_license', 'Driving License'),
    ('other', 'Other'),
]

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_EXT = {'.jpg', '.jpeg', '.png'}
ALLOWED_DOC_EXT = {'.jpg', '.jpeg', '.png', '.pdf'}

REQUIRED_FIELDS = [
    ('applicant_name', 'Full Name'),
    ('mobile', 'Mobile Number (Call)'),
    ('email', 'Email'),
    ('date_of_birth', 'Date of Birth'),
    ('gender', 'Gender'),
    ('membership_type_id', 'Membership Type'),
    ('house_address', 'Address in India'),
    ('state_id', 'State'),
    ('pin_code', 'PIN Code'),
]


def _to_int(value):
    """Safely coerce a value that may be an untrusted browser-supplied
    string (e.g. from a <select>) into an int, never raising and never
    passing a raw string straight into browse() - see the id-coercion
    rule in our Odoo 19 build notes (a raw string id silently misbehaves
    with .browse()).
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def _valid_id(model_name, value):
    """Return the int id if it is a real, existing record of model_name,
    else False. Guards every browser-supplied Many2one id before it is
    written, so a tampered/stale id degrades to False (silently dropped
    for optional fields, or flagged for required ones) instead of
    reaching the ORM and raising an unhandled DB foreign-key error.
    """
    id_ = _to_int(value)
    if not id_:
        return False
    record = request.env[model_name].sudo().browse(id_)
    return id_ if record.exists() else False


class AssociationMembershipWebsite(http.Controller):

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------
    def _get_membership_types(self):
        return request.env['association.membership.type'].sudo().search([('active', '=', True)])

    def _get_countries(self):
        return request.env['res.country'].sudo().search([], order='name')

    def _get_states(self):
        india = request.env.ref('base.in', raise_if_not_found=False)
        domain = [('country_id', '=', india.id)] if india else []
        return request.env['res.country.state'].sudo().search(domain, order='name')

    def _default_values(self, post=None, errors=None):
        return {
            'membership_types': self._get_membership_types(),
            'countries': self._get_countries(),
            'states': self._get_states(),
            'gender_selection': GENDER_SELECTION,
            'blood_groups': BLOOD_GROUPS,
            'id_proof_types': ID_PROOF_TYPES,
            'post': post or {},
            'errors': errors or {},
        }

    def _read_upload(self, files, field_name, allowed_ext, max_size=MAX_UPLOAD_SIZE):
        """Read an uploaded file safely. Returns (base64_content_or_False,
        filename_or_False, error_message_or_None). Never raises.
        """
        upload = files.get(field_name)
        if not upload or not upload.filename:
            return False, False, None
        content = upload.read()
        if not content:
            return False, False, None
        if len(content) > max_size:
            return None, None, _('%s is too large (max %s MB).') % (field_name, max_size // (1024 * 1024))
        ext = os.path.splitext(upload.filename)[1].lower()
        if allowed_ext and ext not in allowed_ext:
            return None, None, _('%s must be one of: %s') % (field_name, ', '.join(sorted(allowed_ext)))
        filename = upload.filename[:256]
        return base64.b64encode(content), filename, None

    # ---------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------
    @http.route('/membership/apply', type='http', auth='public', website=True, sitemap=True)
    def membership_apply(self, **kwargs):
        return request.render(
            'association_membership.membership_apply_page',
            self._default_values(),
        )

    @http.route('/membership/apply/submit', type='http', auth='public',
                website=True, methods=['POST'], sitemap=False)
    def membership_apply_submit(self, **post):
        errors = {}

        for fname, label in REQUIRED_FIELDS:
            if not (post.get(fname) or '').strip():
                errors[fname] = _('%s is required.') % label

        email = (post.get('email') or '').strip()
        if email and not EMAIL_RE.match(email):
            errors['email'] = _('Enter a valid email address.')

        for fname, label in (('mobile', 'Mobile Number (Call)'), ('whatsapp', 'Mobile Number (WhatsApp)')):
            value = (post.get(fname) or '').strip()
            if value:
                digits = ''.join(ch for ch in value if ch.isdigit())
                if len(digits) < 10:
                    errors[fname] = _('%s must contain at least 10 digits.') % label

        pin_code = (post.get('pin_code') or '').strip()
        if pin_code and not pin_code.isdigit():
            errors['pin_code'] = _('PIN Code must contain digits only.')

        membership_type_id = _valid_id('association.membership.type', post.get('membership_type_id'))
        if not membership_type_id:
            errors['membership_type_id'] = _('Please select a valid membership type.')
        else:
            # a membership type must also be active (the dropdown only ever
            # lists active ones, but a stale/tampered value could point at
            # an archived one)
            if not request.env['association.membership.type'].sudo().browse(membership_type_id).active:
                errors['membership_type_id'] = _('Please select a valid membership type.')

        state_id = _valid_id('res.country.state', post.get('state_id'))
        if post.get('state_id') and not state_id:
            errors['state_id'] = _('Please select a valid state.')

        if not post.get('declare_accurate'):
            errors['declare_accurate'] = _('Please confirm the declaration before submitting.')

        if not errors:
            existing = request.env['association.membership.application'].sudo().check_duplicate(
                email=email or None,
                mobile=(post.get('mobile') or '').strip() or None,
                id_proof_number=(post.get('id_proof_number') or '').strip() or None,
                iqama_number=(post.get('iqama_number') or '').strip() or None,
                passport_number=(post.get('passport_number') or '').strip() or None,
            )
            if existing:
                errors['duplicate'] = _(
                    'An application already exists with this email, mobile, Iqama or Passport number '
                    '(Reference: %s). Please contact us if you need help with your existing application.'
                ) % existing.name

        photo_val, photo_name, photo_err = False, False, None
        id_doc_val, id_doc_name, id_doc_err = False, False, None
        if not errors:
            files = request.httprequest.files
            photo_val, photo_name, photo_err = self._read_upload(files, 'photo', ALLOWED_IMAGE_EXT)
            if photo_err:
                errors['photo'] = photo_err
            id_doc_val, id_doc_name, id_doc_err = self._read_upload(files, 'id_proof_document', ALLOWED_DOC_EXT)
            if id_doc_err:
                errors['id_proof_document'] = id_doc_err

        if errors:
            values = self._default_values(post=post, errors=errors)
            return request.render('association_membership.membership_apply_page', values)

        nationality_id = _valid_id('res.country', post.get('nationality_id'))
        country_id = _valid_id('res.country', post.get('country_id'))
        if not country_id:
            india = request.env.ref('base.in', raise_if_not_found=False)
            country_id = india.id if india else False

        vals = {
            'applicant_name': post.get('applicant_name', '').strip(),
            'mobile': post.get('mobile', '').strip(),
            'whatsapp': post.get('whatsapp', '').strip(),
            'email': email,
            'date_of_birth': post.get('date_of_birth') or False,
            'gender': post.get('gender') or False,
            'blood_group': post.get('blood_group') or False,
            'job': post.get('job', '').strip(),
            'nationality_id': nationality_id,
            'iqama_number': post.get('iqama_number', '').strip(),
            'passport_number': post.get('passport_number', '').strip(),
            'ksa_province': post.get('ksa_province', '').strip(),
            'ksa_area': post.get('ksa_area', '').strip(),
            'house_address': post.get('house_address', '').strip(),
            'street': post.get('street', '').strip(),
            'place': post.get('place', '').strip(),
            'district': post.get('district', '').strip(),
            'state_id': state_id,
            'country_id': country_id,
            'pin_code': pin_code,
            'occupation': post.get('occupation', '').strip(),
            'company_name': post.get('company_name', '').strip(),
            'designation': post.get('designation', '').strip(),
            'work_address': post.get('work_address', '').strip(),
            'id_proof_type': post.get('id_proof_type') or False,
            'id_proof_number': post.get('id_proof_number', '').strip(),
            'emergency_contact_name': post.get('emergency_contact_name', '').strip(),
            'emergency_contact_relationship': post.get('emergency_contact_relationship', '').strip(),
            'emergency_contact_mobile': post.get('emergency_contact_mobile', '').strip(),
            'membership_type_id': membership_type_id,
            'membership_category': post.get('membership_category', '').strip(),
            'referral_reference': post.get('referral_reference', '').strip(),
            'additional_info': post.get('additional_info', '').strip(),
        }
        if photo_val:
            vals['photo'] = photo_val
        if id_doc_val:
            vals['id_proof_document'] = id_doc_val
            vals['id_proof_document_name'] = id_doc_name

        Application = request.env['association.membership.application'].sudo()
        try:
            application = Application.create(vals)
            application.action_submit()
        except (ValidationError, UserError) as exc:
            errors['general'] = exc.args[0] if exc.args else str(exc)
            values = self._default_values(post=post, errors=errors)
            return request.render('association_membership.membership_apply_page', values)

        return request.redirect('/membership/apply/thank-you?ref=%s' % quote(application.name, safe=''))

    @http.route('/membership/apply/thank-you', type='http', auth='public', website=True, sitemap=False)
    def membership_apply_thanks(self, ref=None, **kwargs):
        application = request.env['association.membership.application'].sudo()
        if ref:
            application = application.search([('name', '=', ref)], limit=1)
        return request.render('association_membership.membership_apply_thanks', {
            'application': application,
        })

    @http.route('/membership/verify/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def membership_verify(self, token, **kwargs):
        """Public digital-card verification page. Looks the member up by
        their unguessable card_token (never by id/member_number, which are
        sequential and easy to enumerate) and shows only what a verifier
        needs - never mobile, address, Iqama/Passport or any other PII.
        """
        member = request.env['association.member'].sudo().search(
            [('card_token', '=', token)], limit=1) if token else request.env['association.member']
        return request.render('association_membership.membership_verify_page', {
            'member': member,
        })
