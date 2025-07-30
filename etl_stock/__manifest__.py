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
    'name': 'Inventory',
    'version': '16.0.1.0.0',
    'summary': 'Inventory',
    'description': """Inventory""",
    'category': 'Inventory/Inventory',
    'author': 'Steigend IT Solutions',
    'company': 'Steigend IT Solutions',
    'maintainer': 'Steigend IT Solutions',
    'website': 'https://www.steigendit.com',
    'depends': [
        'branch', 
        'product', 
        'stock', 
        'stock_account', 
        'etl_sale', 
        'account_lock', 
        'mail'
        ],
    'data': [
        'views/product_view.xml',
        'views/company_view.xml',
        'security/ir.model.access.csv',
        'views/picking_view.xml',
        'views/lot_view.xml',
        'reports/serial_number_label.xml',
        'reports/packing_slip.xml',
        'reports/delivery_challan.xml',
        'wizard/reconcile_report_view.xml',
        'wizard/stock_ageing_view.xml',
        'wizard/serial_report_view.xml',
        'data/cron.xml'
        ],
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
