from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.http import request

PAYMENTS_PER_PAGE = 20


class AssociationMembershipPortal(CustomerPortal):

    def _get_portal_member(self):
        """The association.member record for the logged-in portal user's
        contact, or an empty recordset if they have none. ir.rule already
        scopes association.member reads to the user's own partner_id, so a
        plain search (no sudo) can never return someone else's record.
        """
        partner = request.env.user.partner_id
        return request.env['association.member'].search([('partner_id', '=', partner.id)], limit=1)

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'membership_count' in counters:
            values['membership_count'] = 1 if self._get_portal_member() else 0
        return values

    @http.route(['/my/membership'], type='http', auth='user', website=True)
    def portal_my_membership(self, **kw):
        member = self._get_portal_member()
        values = self._prepare_portal_layout_values()
        values.update({
            'member': member,
            'membership': member.current_membership_id if member else request.env['association.membership'],
            'membership_history': member.membership_ids.sorted('start_date', reverse=True) if member else [],
            'page_name': 'membership',
        })
        return request.render('association_membership.portal_my_membership', values)

    @http.route(['/my/membership/payments', '/my/membership/payments/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_membership_payments(self, page=1, **kw):
        member = self._get_portal_member()
        Payment = request.env['association.membership.payment']
        domain = [('member_id', '=', member.id)] if member else [('id', '=', 0)]

        payment_count = Payment.search_count(domain)
        pager = portal_pager(
            url='/my/membership/payments',
            total=payment_count,
            page=page,
            step=PAYMENTS_PER_PAGE,
        )
        payments = Payment.search(
            domain, order='payment_date desc, id desc',
            limit=PAYMENTS_PER_PAGE, offset=pager['offset'],
        )
        values = self._prepare_portal_layout_values()
        values.update({
            'member': member,
            'payments': payments,
            'pager': pager,
            'page_name': 'membership_payments',
        })
        return request.render('association_membership.portal_my_membership_payments', values)

    @http.route(['/my/membership/card'], type='http', auth='user', website=True)
    def portal_my_membership_card(self, **kw):
        member = self._get_portal_member()
        if member and member.digital_card_enabled and member.status in ('active', 'suspended', 'expired'):
            # Portal users only ever have read access to association.member
            # (see the portal ir.rule/ACL); token issuance is a narrow,
            # server-controlled side effect, not an open write, so sudo() is
            # safe here - the member was already resolved to the logged-in
            # user's own partner_id above.
            member.sudo()._ensure_card_token()
            member = member.sudo()
        values = self._prepare_portal_layout_values()
        values.update({
            'member': member,
            'page_name': 'membership_card',
        })
        return request.render('association_membership.portal_my_membership_card', values)
