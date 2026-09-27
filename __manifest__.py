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
* Digital membership card with QR verification (added in Phase 5)
* Member portal, self-renewal, expiry reminders (added in Phase 4/6)

This delivery covers Phase 1 (data model, sequences, security, backend
screens), Phase 2 (the public, multi-step, validated /membership/apply
website form with document upload and duplicate-application checking) and
Phase 3 (association.membership.payment: manual payment recording with a
draft-confirm-refund workflow, automatically created when an application
is sent for payment or a membership is renewed with a fee due, and wired
back to advance the application/membership state on confirmation. Includes
gateway-ready fields, unused today, for a future Razorpay/Stripe
integration).
""",
    'author': 'Otomater',
    'website': 'https://otomater.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'website',
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
        'views/association_membership_menus.xml',
        'views/website_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
