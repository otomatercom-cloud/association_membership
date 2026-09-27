{
    'name': 'Association Membership Management',
    'version': '19.0.1.0.0',
    'category': 'Customizations',
    'summary': 'Public application, verification, payment, approval, digital card and renewal lifecycle for association members',
    'description': """
Association Membership Management
==================================

Manages the complete membership lifecycle for an association, club or society:

* Public membership application at /membership/apply (Phase 2)
* Admin verification and approval workflow
* Membership fee / payment recording and confirmation workflow (Phase 3)
* Member and membership records, linked to res.partner
* Member self-service portal at /my/membership (Phase 4)
* Digital membership card with public QR verification (Phase 5)
* Renewal reminders / expiry cron (added in Phase 6)

This delivery covers Phase 1 (data model, sequences, security, backend
screens), Phase 2 (the public, multi-step, validated /membership/apply
website form with document upload and duplicate-application checking),
Phase 3 (association.membership.payment: manual payment recording with a
draft-confirm-refund workflow, automatically created when an application
is sent for payment or a membership is renewed with a fee due, and wired
back to advance the application/membership state on confirmation; includes
gateway-ready fields, unused today, for a future Razorpay/Stripe
integration), Phase 4 (a "Grant Portal Access" button on the Member record
creates/invites a portal user for that member's contact; once logged in,
the member sees their profile, current membership and status, and full
payment history at /my/membership and /my/membership/payments, strictly
scoped to their own record via record rules) and Phase 5 (an ID-1 sized
QWeb PDF "Digital Membership Card" with the member's photo and a QR code
that links to a public, no-login verification page at
/membership/verify/<token>, showing only membership status - never
mobile, address or ID numbers; card issuance is per membership type via
the existing "Digital Card Enabled" toggle and the token is generated
automatically the moment a membership is activated).
""",
    'author': 'Otomater',
    'website': 'https://otomater.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'website',
        'portal',
    ],
    'data': [
        'security/association_membership_security.xml',
        'security/ir.model.access.csv',
        'data/association_membership_sequence_data.xml',
        'views/association_membership_type_views.xml',
        'views/association_membership_application_views.xml',
        'views/association_member_views.xml',
        'views/association_membership_views.xml',
        'views/association_membership_payment_views.xml',
        'report/membership_card_templates.xml',
        'views/association_membership_menus.xml',
        'views/website_templates.xml',
        'views/website_card_templates.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
