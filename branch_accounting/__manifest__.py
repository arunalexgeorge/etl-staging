# -*- coding: utf-8 -*-

{
    "name": "Multi Branch Accounting",
    "version": "16.0.0.0",
    "category": "Accounting",
    'summary': 'Multiple Branch Accounting',
    "description": """Multiple Branch Accounting.""",
    "author": "Steigend IT Solutions",
    "website": "https://www.steigendit.com",
    "price": 0,
    "currency": 'EUR',
    "depends": ['account', 'account_accountant', 'account_reports', 'branch'],
    "data": [
        'data/accounts_report_data.xml',
        'data/accounts_report_column.xml',
        'views/search_template_view.xml',
        'views/inherited_account_bank_statement.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'branch_accounting/static/src/js/custom_account_reports.js',
        ],
    },
    'qweb': [],
    "auto_install": False,
    "installable": True,
    'license': 'OPL-1',
    'live_test_url': 'https://youtu.be/_z5XH1mdtwk',
    "images": ['static/description/Banner.gif'],
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
