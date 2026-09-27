{
    'name': 'Association Membership Management',
    'version': '19.0.1.0.0',
    'category': 'Customizations',
    'summary': 'Public application, verification, payment, approval, digital card and renewal lifecycle for association members',
    'description': """
Association Membership Management
==================================

Manages the complete membership lifecycle for an association, club or society:

* Public membership application (added in Phase 2)
* Admin verification and approval workflow
* Membership fee / payment tracking (extended in Phase 3)
* Member and membership records, linked to res.partner
* Digital membership card with QR verification (added in Phase 5)
* Member portal, self-renewal, expiry reminders (added in Phase 4/6)

This is the Phase 1 delivery: data model, sequences, security and backend
management screens for Membership Types, Applications, Members and
Memberships.
""",
    'author': 'Otomater',
    'website': 'https://otomater.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
    ],
    'data': [
        'security/association_membership_security.xml',
        'security/ir.model.access.csv',
        'data/association_membership_sequence_data.xml',
        'views/association_membership_type_views.xml',
        'views/association_membership_application_views.xml',
        'views/association_member_views.xml',
        'views/association_membership_views.xml',
        'views/association_membership_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
