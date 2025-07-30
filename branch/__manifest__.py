# -*- coding: utf-8 -*-
#############################################################################
#
#    Steigend IT Solutions.
#
#    Copyright (C) 2023-TODAY Steigend IT Solutions.
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

{
    'name': 'Multiple Branches',
    'version': '16.0.0.1',
    'category': 'Sales',
    'summary': 'Multiple Branches',
    "description": """
       Multiple Branches
       """,
    "author": "Steigend IT Solutions",
    "website": "https://www.steigendit.com",
    "price": 0,
    "currency": 'EUR',
    'depends': ['base', 'sale_management', 'purchase', 'stock', 'account', 'purchase_stock','web'],
    'uninstall_hook': '_uninstall_hook',
    'data': [
        'security/branch_security.xml',
        'security/ir.model.access.csv',
        'views/res_branch_view.xml',
        'views/res_users_view.xml',
        'views/sale_order_view.xml',
        'views/stock_picking_view.xml',
        'views/stock_move_view.xml',
        'views/account_move_view.xml',
        'views/purchase_order_view.xml',
        'views/stock_warehouse_view.xml',
        'views/stock_location_view.xml',
        'wizard/account_payment_view.xml',
        'views/product_view.xml',
        'views/partner_view.xml',
        'views/stock_quant_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'branch/static/src/js/session.js',
            'branch/static/src/js/branch_service.js',
            'branch/static/src/xml/branch.xml'
        ]
    },
    'license' : 'OPL-1',
    'demo': [],
    'test': [],
    'installable': True,
    'auto_install': False,
    'live_test_url':'https://youtu.be/hi1b8kH5Z94',
    "images":['static/description/Banner.gif'],
    'post_init_hook': 'post_init_hook',
}

