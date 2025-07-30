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
    'name': 'Quality',
    'version': '16.0.1.0.0',
    'summary': 'Quality',
    'description': """Quality""",
    'category': 'Manufacturing/Quality',
    'author': 'Steigend IT Solutions',
    'company': 'Steigend IT Solutions',
    'maintainer': 'Steigend IT Solutions',
    'website': 'https://www.steigendit.com',
    'depends': ['stock', 'mrp', 'etl_sale'],
    'data': [
        'views/parameter_view.xml',
        'views/qc_view.xml',
        'views/picking_view.xml',
        'views/quality_overview_view.xml',
        'views/mrp_view.xml',
        'data/data.xml',
        'security/ir.model.access.csv',
        'security/security.xml',
        'reports/qc_check_report_view.xml',
        'reports/grn_qc_report_template_view.xml',
        'reports/mo_qc_report_template_view.xml'
        ],
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
