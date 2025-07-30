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
    'name': 'Base',
    'version': '16.0.1.0.0',
    'summary': 'Generic Features',
    'description': """Generic Features""",
    'category': 'Extra Tools',
    'author': 'Steigend IT Solutions',
    'company': 'Steigend IT Solutions',
    'maintainer': 'Steigend IT Solutions',
    'website': 'https://www.steigendit.com',
    'depends': [
        'base', 
        'contacts', 
        'account', 
        'l10n_in', 
        'sales_team', 
        'hr', 
        'mrp', 
        'purchase',
        'stock',
        'product',
        'portal',
        'branch'
        ],
    'data': [
        'data/sequence.xml',
        'views/partner_view.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/employee_view.xml',
        'reports/report_layout.xml'
        ],
    'assets': {
        'web.assets_backend': [
            'etl_base/static/src/js/action_manager.js',
            'etl_base/static/src/scss/field.scss',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
