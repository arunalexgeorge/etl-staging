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
    'name': 'Manufacturing',
    'version': '16.0.1.0.0',
    'summary': 'Manufacturing',
    'description': """Manufacturing""",
    'category': 'Manufacturing/Manufacturing',
    'author': 'Steigend IT Solutions',
    'company': 'Steigend IT Solutions',
    'maintainer': 'Steigend IT Solutions',
    'website': 'https://www.steigendit.com',
    'depends': ['mrp', 'stock', 'etl_stock', 'etl_quality', 'mrp_account_enterprise'],
    'data': [
        'wizard/change_batch_qty.xml',
        'wizard/production_planning_view.xml',
        'views/mrp_view.xml',
        'security/ir.model.access.csv',
        'reports/serial_number_label.xml'
        ],
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
