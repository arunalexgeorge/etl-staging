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
    'name': 'Accounting',
    'version': '16.0.1.0.0',
    'summary': 'Accounting',
    'description': """Accounting""",
    'category': 'Invoices & Payments',
    'author': 'Steigend IT Solutions',
    'company': 'Steigend IT Solutions',
    'maintainer': 'Steigend IT Solutions',
    'website': 'https://www.steigendit.com',
    'depends': [
        'account', 
        'account_batch_payment',
        'sale', 
        'l10n_in', 
        'hr', 
        'etl_base', 
        'etl_sale', 
        'account_reports', 
        'etl_stock',
        'stock_account',
        'web'
        ],
    'data': [
        'wizard/statement_import_view.xml',
        'wizard/bank_rec_view.xml',
        'wizard/partner_ledger_view.xml',
        'views/partner_view.xml',
        'views/move_view.xml',
        'views/journal_view.xml',
        'views/company_view.xml',
        'views/payment_view.xml',
        # 'views/pnl.xml',
        'security/ir.model.access.csv',
        'wizard/sales_report_view.xml',
        'wizard/purchase_report_view.xml',
        'wizard/hsn_report_view.xml',
        'wizard/document_summary_view.xml',
        'reports/report_invoice.xml',
        'reports/report_ledger.xml',
        'reports/report_payment.xml',
        'reports/report_voucher.xml'
        ],
    'license': 'AGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
