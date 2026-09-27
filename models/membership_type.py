from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields, models


class AssociationMembershipType(models.Model):
    _name = 'association.membership.type'
    _description = 'Association Membership Type'
    _order = 'sequence, name'

    name = fields.Char(string='Membership Type', required=True)
    code = fields.Char(string='Code', required=True)
    description = fields.Text(string='Description')
    sequence = fields.Integer(string='Sequence', default=10)

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id, required=True,
    )
    membership_fee = fields.Monetary(string='Membership Fee', currency_field='currency_id', required=True, default=0.0)
    renewal_fee = fields.Monetary(string='Renewal Fee', currency_field='currency_id', default=0.0)
    joining_fee = fields.Monetary(string='Joining Fee', currency_field='currency_id', default=0.0)
    tax_percentage = fields.Float(string='Tax (%)', default=0.0)

    duration = fields.Integer(string='Duration', required=True, default=1)
    duration_unit = fields.Selection(
        [
            ('days', 'Days'),
            ('months', 'Months'),
            ('years', 'Years'),
        ],
        string='Duration Unit', required=True, default='years',
    )

    active = fields.Boolean(string='Active', default=True)
    requires_approval = fields.Boolean(
        string='Requires Final Approval', default=True,
        help='If enabled, a paid application still needs an explicit final approval '
             'before the membership becomes Active.',
    )
    digital_card_enabled = fields.Boolean(string='Digital Card Enabled', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _code_uniq = models.Constraint(
        'unique(code, company_id)',
        'Membership Type code must be unique per company.',
    )

    def get_expiry_date(self, start_date):
        """Return the expiry date for this membership type starting on start_date.

        A membership of duration N (days/months/years) is considered valid
        THROUGH the day before the next cycle would start, matching common
        association practice (e.g. 01/10/2026 - 30/09/2027 for a 1 year type).
        """
        self.ensure_one()
        if self.duration_unit == 'days':
            delta = relativedelta(days=self.duration)
        elif self.duration_unit == 'months':
            delta = relativedelta(months=self.duration)
        else:
            delta = relativedelta(years=self.duration)
        return start_date + delta - timedelta(days=1)
