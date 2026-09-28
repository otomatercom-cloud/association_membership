from odoo import api, models


class AssociationMembershipDashboard(models.AbstractModel):
    """Read-only aggregation model backing the OWL Membership Dashboard
    client action. Deliberately does all counting/summing in Python on the
    server (search_count / read_group via ORM) rather than in JS, so the
    OWL side only needs one RPC call and a couple of plain dicts to render -
    see erp-tooling-3.md finding #71 (Odoo 19 renamed the JS ORM service's
    readGroup to formattedReadGroup with a different result shape); doing
    the aggregation server-side sidesteps that entirely.
    """
    _name = 'association.membership.dashboard'
    _description = 'Association Membership Dashboard'

    @api.model
    def get_dashboard_data(self):
        Member = self.env['association.member']
        Payment = self.env['association.membership.payment']
        Application = self.env['association.membership.application']
        MembershipType = self.env['association.membership.type']

        member_status_counts = {}
        for status, _label in Member._fields['status'].selection:
            member_status_counts[status] = Member.search_count([('status', '=', status)])
        total_members = sum(member_status_counts.values())

        valid_card_members = Member.search_count([('card_status', '=', 'active')])
        expired_card_members = Member.search_count([('card_status', '=', 'expired')])

        pending_applications = Application.search_count(
            [('state', 'in', ('submitted', 'under_verification', 'payment_pending'))])
        approved_applications = Application.search_count([('state', '=', 'approved')])
        rejected_applications = Application.search_count([('state', '=', 'rejected')])

        paid_count = Payment.search_count([('state', '=', 'confirmed')])
        pending_payment_count = Payment.search_count([('state', 'in', ('draft', 'pending'))])
        failed_payment_count = Payment.search_count([('state', 'in', ('failed', 'cancelled'))])

        confirmed_payments = Payment.search([('state', '=', 'confirmed')])
        pending_payments = Payment.search([('state', 'in', ('draft', 'pending'))])
        total_collected = sum(confirmed_payments.mapped('total_amount'))
        total_pending_amount = sum(pending_payments.mapped('total_amount'))

        membership_types = []
        for mt in MembershipType.search([]):
            count = Member.search_count([('membership_type_id', '=', mt.id)])
            if count:
                membership_types.append({'name': mt.name, 'count': count})
        membership_types.sort(key=lambda d: d['count'], reverse=True)

        currency = self.env.company.currency_id

        return {
            'total_members': total_members,
            'active_members': member_status_counts.get('active', 0),
            'expired_members': member_status_counts.get('expired', 0),
            'suspended_members': member_status_counts.get('suspended', 0),
            'cancelled_members': member_status_counts.get('cancelled', 0),
            'draft_members': member_status_counts.get('draft', 0),
            'valid_card_members': valid_card_members,
            'expired_card_members': expired_card_members,
            'pending_applications': pending_applications,
            'approved_applications': approved_applications,
            'rejected_applications': rejected_applications,
            'paid_count': paid_count,
            'pending_payment_count': pending_payment_count,
            'failed_payment_count': failed_payment_count,
            'total_collected': total_collected,
            'total_pending_amount': total_pending_amount,
            'currency_symbol': currency.symbol or '',
            'currency_position': currency.position or 'before',
            'membership_types': membership_types,
        }
