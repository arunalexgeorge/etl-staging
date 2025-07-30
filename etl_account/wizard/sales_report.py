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

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang, xlwt
from io import BytesIO
import base64
         
class SalesRegister(models.TransientModel):
    _name = 'sale.register'
    _description = 'Sales Register' 

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    branch_ids = fields.Many2many('res.branch', string='Branches')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    
    @api.model
    def default_get(self, default_fields):
        res = super(SalesRegister, self).default_get(default_fields)
        res.update({'branch_ids' : self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)})
        return res
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Sales Register')
        title_centre = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_left_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz left, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_blank = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_300 = xlwt.easyxf('font: height 300, name Arial, colour_index black, bold on; align: horiz centre, vert centre;border: bottom thin, top thin, left thin, right thin')
        title_left = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz left;')
        string_left = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz left;')
        string_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;')
        number_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;',num_format_str='#,##0;-#,##0')
        string_left_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz left;')
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_bold_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        ws.col(1).width = 9000
        for i in range(0, 22):
            if i != 1:
                ws.col(i).width = 4000
        ws.write_merge(0, 0, 0, 21, 'Sales Register', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(1, 1, 0, 21, date, title_left_bg)
        col = 2
        ws.write(col, 0, 'Date', title_centre)
        ws.write(col, 1, 'Particulars', title_centre)
        ws.write(col, 2, 'Voucher Type', title_centre)
        ws.write(col, 3, 'Voucher Number', title_centre)
        ws.write(col, 4, 'GSTIN/UIN', title_centre)
        ws.write(col, 5, 'Place of Supply', title_centre)
        ws.write(col, 6, 'Quantity', title_centre)
        ws.write(col, 7, 'Value', title_centre)
        ws.write(col, 8, 'Gross Total', title_centre)
        ws.write(col, 9, 'Sales Accounts', title_centre)
        ws.write(col, 10, 'CGST-2.5', title_centre)
        ws.write(col, 11, 'SGST-2.5', title_centre)
        ws.write(col, 12, 'CGST-9', title_centre)
        ws.write(col, 13, 'SGST-9', title_centre)
        ws.write(col, 14, 'CGST-14', title_centre)
        ws.write(col, 15, 'SGST-14', title_centre)
        ws.write(col, 16, 'IGST-18', title_centre)
        ws.write(col, 17, 'TCS', title_centre)
        ws.write(col, 18, 'Freight Charges', title_centre)
        ws.write(col, 19, 'Discount', title_centre)
        ws.write(col, 20, 'Round Off', title_centre)
        ws.write(col, 21, 'Invoice Status', title_centre)
        col = 3
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', '!=', 'draft'),
            ('branch_id', 'in', [branch.id for branch in self.branch_ids])
            ], order='invoice_date,name')
        total_cgst_25, total_cgst_9, total_cgst_14 = 0.0, 0.0, 0.0
        total_sgst_25, total_sgst_9, total_sgst_14 = 0.0, 0.0, 0.0
        total_igst_18, total_round_off, total_amount_taxed = 0.0, 0.0, 0.0
        total_amount_untaxed, total_sales_account, total_tcs = 0.0, 0.0, 0.0
        total_qty = 0.0
        for invoice in invoices:
            cgst_25, cgst_9, cgst_14 = 0.0, 0.0, 0.0
            sgst_25, sgst_9, sgst_14 = 0.0, 0.0, 0.0
            igst_18, tax_perc, round_off = 0.0, 0.0, 0.0
            qty, tcs = 0, 0
            
            sales_account = 0.0
            group, tcs = False, False
            
            if invoice.state == 'cancel':
                ws.write(col, 0, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Invoice', string_left)
                ws.write(col, 3, invoice.name, string_left)
                ws.write(col, 4, invoice.partner_id.vat or '', string_left)
                ws.write(col, 5, invoice.partner_id.state_id and invoice.partner_id.state_id.name or '', string_left)
                ws.write(col, 6, '', number2d)
                ws.write(col, 7, '', number2d)
                ws.write(col, 8, '', number2d)
                ws.write(col, 9, '', number2d)
                ws.write(col, 10, '', number2d)
                ws.write(col, 11, '', number2d)
                ws.write(col, 12, '', number2d)
                ws.write(col, 13, '', number2d)
                ws.write(col, 14, '', number2d)
                ws.write(col, 15, '', number2d)
                ws.write(col, 16, '', number2d)
                ws.write(col, 17, '', number2d)
                ws.write(col, 18, '', number2d)
                ws.write(col, 19, '', number2d)
                ws.write(col, 20, '', number2d)
                ws.write(col, 21, 'CANCELLED', string_left)
                col += 1
            else:
                for line in invoice.invoice_line_ids:
                    qty += line.quantity
                    if line.display_type == 'product':
                        sales_account += line.price_subtotal
                    if not group:
                        if line.tax_ids:
                            tax = line.tax_ids[0]
                            tax_perc = tax.amount
                            group = tax.tax_group_id.name
                            
                tax_totals = invoice.tax_totals
                amount_by_group_list = tax_totals['groups_by_subtotal'].values()
                for a in amount_by_group_list:
                    for b in a:
                        tax_amount = b['tax_group_amount']
                        if b['tax_group_name'] == 'SGST':
                            if tax_perc == 5:
                                cgst_25 = tax_amount
                                sgst_25 = tax_amount
                            elif tax_perc == 18:
                                cgst_9 = tax_amount
                                sgst_9 = tax_amount
                            elif tax_perc == 28:
                                cgst_14 = tax_amount
                                sgst_14 = tax_amount
                        elif b['tax_group_name'] == 'IGST':
                            igst_18 = tax_amount
                        elif b['tax_group_name'] == 'TCS':
                            tcs = tax_amount
                        
                rounding_line = invoice.line_ids.filtered(lambda l: l.display_type == 'rounding')
                
                if rounding_line:
                    round_off = -1 * rounding_line.balance
                    
                amount_untaxed = invoice.amount_untaxed_signed
                amount_total = invoice.amount_total_signed
                total_qty += qty
                total_cgst_25 += cgst_25
                total_sgst_25 += sgst_25
                total_cgst_9 += cgst_9
                total_sgst_9 += sgst_9
                total_cgst_14 += cgst_14
                total_sgst_14 += sgst_14
                total_igst_18 += igst_18
                total_tcs += tcs
                total_round_off += round_off
                total_amount_untaxed += amount_untaxed
                total_sales_account += sales_account
                total_amount_taxed += amount_total
                
                ws.write(col, 0, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Invoice', string_left)
                ws.write(col, 3, invoice.name, string_left)
                ws.write(col, 4, invoice.partner_id.vat or '', string_left)
                ws.write(col, 5, invoice.partner_id.state_id and invoice.partner_id.state_id.name or '', string_left)
                ws.write(col, 6, qty or '', number2d)
                ws.write(col, 7, amount_untaxed, number2d)
                ws.write(col, 8, amount_total, number2d)
                ws.write(col, 9, sales_account, number2d)
                ws.write(col, 10, cgst_25 or '', number2d)
                ws.write(col, 11, sgst_25 or '', number2d)
                ws.write(col, 12, cgst_9 or '', number2d)
                ws.write(col, 13, sgst_9 or '', number2d)
                ws.write(col, 14, cgst_14 or '', number2d)
                ws.write(col, 15, sgst_14 or '', number2d)
                ws.write(col, 16, igst_18 or '', number2d)
                ws.write(col, 17, tcs or '', number2d)
                ws.write(col, 18, '', number2d)
                ws.write(col, 19, '', number2d)
                ws.write(col, 20, round_off or '', number2d)
                ws.write(col, 21, 'POSTED', string_left)
                col += 1
        ws.write(col, 6, total_qty or '', number2d_bold_bg)
        ws.write(col, 7, total_amount_untaxed or '', number2d_bold_bg)
        ws.write(col, 8, total_amount_taxed or '', number2d_bold_bg)
        ws.write(col, 9, total_sales_account or '', number2d_bold_bg)
        ws.write(col, 10, total_cgst_25 or '', number2d_bold_bg)
        ws.write(col, 11, total_sgst_25 or '', number2d_bold_bg)
        ws.write(col, 12, total_cgst_9 or '', number2d_bold_bg)
        ws.write(col, 13, total_sgst_9 or '', number2d_bold_bg)
        ws.write(col, 14, total_cgst_14 or '', number2d_bold_bg)
        ws.write(col, 15, total_sgst_14 or '', number2d_bold_bg)
        ws.write(col, 16, total_igst_18 or '', number2d_bold_bg)
        ws.write(col, 17, total_tcs or '', number2d_bold_bg)
        ws.write(col, 18, '', number2d_bold_bg)
        ws.write(col, 19, '', number2d_bold_bg)
        ws.write(col, 20, total_round_off or '', number2d_bold_bg)
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Sales Register.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/sales/register?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    
    def action_print_cn(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Credit Note Register')
        title_centre = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_left_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz left, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_blank = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_300 = xlwt.easyxf('font: height 300, name Arial, colour_index black, bold on; align: horiz centre, vert centre;border: bottom thin, top thin, left thin, right thin')
        title_left = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz left;')
        string_left = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz left;')
        string_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;')
        number_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;',num_format_str='#,##0;-#,##0')
        string_left_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz left;')
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_bold_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        ws.col(1).width = 9000
        for i in range(0, 22):
            if i != 1:
                ws.col(i).width = 4000
        ws.write_merge(0, 0, 0, 21, 'Credit Note Register', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(1, 1, 0, 21, date, title_left_bg)
        col = 2
        ws.write(col, 0, 'Date', title_centre)
        ws.write(col, 1, 'Particulars', title_centre)
        ws.write(col, 2, 'Voucher Type', title_centre)
        ws.write(col, 3, 'Voucher Number', title_centre)
        ws.write(col, 4, 'GSTIN/UIN', title_centre)
        ws.write(col, 5, 'Place of Supply', title_centre)
        ws.write(col, 6, 'Quantity', title_centre)
        ws.write(col, 7, 'Value', title_centre)
        ws.write(col, 8, 'Gross Total', title_centre)
        ws.write(col, 9, 'Taxable Value', title_centre)
        ws.write(col, 10, 'CGST-2.5', title_centre)
        ws.write(col, 11, 'SGST-2.5', title_centre)
        ws.write(col, 12, 'CGST-9', title_centre)
        ws.write(col, 13, 'SGST-9', title_centre)
        ws.write(col, 14, 'CGST-14', title_centre)
        ws.write(col, 15, 'SGST-14', title_centre)
        ws.write(col, 16, 'IGST-18', title_centre)
        ws.write(col, 17, 'TCS', title_centre)
        ws.write(col, 18, 'Freight Charges', title_centre)
        ws.write(col, 19, 'Discount', title_centre)
        ws.write(col, 20, 'Round Off', title_centre)
        ws.write(col, 21, 'Status', title_centre)
        col = 3
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_refund'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', '!=', 'draft'),
            ('branch_id', 'in', [branch.id for branch in self.branch_ids])
            ], order='invoice_date,name')
        total_cgst_25, total_cgst_9, total_cgst_14 = 0.0, 0.0, 0.0
        total_sgst_25, total_sgst_9, total_sgst_14 = 0.0, 0.0, 0.0
        total_igst_18, total_round_off, total_amount_taxed = 0.0, 0.0, 0.0
        total_amount_untaxed, total_sales_account, total_tcs = 0.0, 0.0, 0.0
        total_qty = 0.0
        for invoice in invoices:
            cgst_25, cgst_9, cgst_14 = 0.0, 0.0, 0.0
            sgst_25, sgst_9, sgst_14 = 0.0, 0.0, 0.0
            igst_18, tax_perc, round_off = 0.0, 0.0, 0.0
            qty, tcs = 0, 0
            
            sales_account = 0.0
            group, tcs = False, False
            
            if invoice.state == 'cancel':
                ws.write(col, 0, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Credit Note', string_left)
                ws.write(col, 3, invoice.name, string_left)
                ws.write(col, 4, invoice.partner_id.vat or '', string_left)
                ws.write(col, 5, invoice.partner_id.state_id and invoice.partner_id.state_id.name or '', string_left)
                ws.write(col, 6, '', number2d)
                ws.write(col, 7, '', number2d)
                ws.write(col, 8, '', number2d)
                ws.write(col, 9, '', number2d)
                ws.write(col, 10, '', number2d)
                ws.write(col, 11, '', number2d)
                ws.write(col, 12, '', number2d)
                ws.write(col, 13, '', number2d)
                ws.write(col, 14, '', number2d)
                ws.write(col, 15, '', number2d)
                ws.write(col, 16, '', number2d)
                ws.write(col, 17, '', number2d)
                ws.write(col, 18, '', number2d)
                ws.write(col, 19, '', number2d)
                ws.write(col, 20, '', number2d)
                ws.write(col, 21, 'CANCELLED', string_left)
                col += 1
            else:
                for line in invoice.invoice_line_ids:
                    qty += line.quantity
                    if line.display_type == 'product':
                        sales_account += line.price_subtotal
                    if not group:
                        if line.tax_ids:
                            tax = line.tax_ids[0]
                            tax_perc = tax.amount
                            group = tax.tax_group_id.name
                            
                tax_totals = invoice.tax_totals
                amount_by_group_list = tax_totals['groups_by_subtotal'].values()
                for a in amount_by_group_list:
                    for b in a:
                        tax_amount = b['tax_group_amount']
                        if b['tax_group_name'] == 'SGST':
                            if tax_perc == 5:
                                cgst_25 = tax_amount
                                sgst_25 = tax_amount
                            elif tax_perc == 18:
                                cgst_9 = tax_amount
                                sgst_9 = tax_amount
                            elif tax_perc == 28:
                                cgst_14 = tax_amount
                                sgst_14 = tax_amount
                        elif b['tax_group_name'] == 'IGST':
                            igst_18 = tax_amount
                        elif b['tax_group_name'] == 'TCS':
                            tcs = tax_amount
                        
                rounding_line = invoice.line_ids.filtered(lambda l: l.display_type == 'rounding')
                
                if rounding_line:
                    round_off = rounding_line.balance
                    
                amount_untaxed = invoice.amount_untaxed_signed*-1
                amount_total = invoice.amount_total_signed*-1
                total_qty += qty
                total_cgst_25 += cgst_25
                total_sgst_25 += sgst_25
                total_cgst_9 += cgst_9
                total_sgst_9 += sgst_9
                total_cgst_14 += cgst_14
                total_sgst_14 += sgst_14
                total_igst_18 += igst_18
                total_tcs += tcs
                total_round_off += round_off
                total_amount_untaxed += amount_untaxed
                total_sales_account += sales_account
                total_amount_taxed += amount_total
                
                ws.write(col, 0, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Credit Note', string_left)
                ws.write(col, 3, invoice.name, string_left)
                ws.write(col, 4, invoice.partner_id.vat or '', string_left)
                ws.write(col, 5, invoice.partner_id.state_id and invoice.partner_id.state_id.name or '', string_left)
                ws.write(col, 6, qty or '', number2d)
                ws.write(col, 7, amount_untaxed, number2d)
                ws.write(col, 8, amount_total, number2d)
                ws.write(col, 9, sales_account, number2d)
                ws.write(col, 10, cgst_25 or '', number2d)
                ws.write(col, 11, sgst_25 or '', number2d)
                ws.write(col, 12, cgst_9 or '', number2d)
                ws.write(col, 13, sgst_9 or '', number2d)
                ws.write(col, 14, cgst_14 or '', number2d)
                ws.write(col, 15, sgst_14 or '', number2d)
                ws.write(col, 16, igst_18 or '', number2d)
                ws.write(col, 17, tcs or '', number2d)
                ws.write(col, 18, '', number2d)
                ws.write(col, 19, '', number2d)
                ws.write(col, 20, round_off or '', number2d)
                ws.write(col, 21, 'POSTED', string_left)
                col += 1
        ws.write(col, 6, total_qty or '', number2d_bold_bg)
        ws.write(col, 7, total_amount_untaxed or '', number2d_bold_bg)
        ws.write(col, 8, total_amount_taxed or '', number2d_bold_bg)
        ws.write(col, 9, total_sales_account or '', number2d_bold_bg)
        ws.write(col, 10, total_cgst_25 or '', number2d_bold_bg)
        ws.write(col, 11, total_sgst_25 or '', number2d_bold_bg)
        ws.write(col, 12, total_cgst_9 or '', number2d_bold_bg)
        ws.write(col, 13, total_sgst_9 or '', number2d_bold_bg)
        ws.write(col, 14, total_cgst_14 or '', number2d_bold_bg)
        ws.write(col, 15, total_sgst_14 or '', number2d_bold_bg)
        ws.write(col, 16, total_igst_18 or '', number2d_bold_bg)
        ws.write(col, 17, total_tcs or '', number2d_bold_bg)
        ws.write(col, 18, '', number2d_bold_bg)
        ws.write(col, 19, '', number2d_bold_bg)
        ws.write(col, 20, total_round_off or '', number2d_bold_bg)
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Credit Note Register.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/sales/register?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }

    def action_print_rt(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('SALES RATEWISE TURNOVER')
        title_centre = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_left_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on; align: horiz left, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_blank = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz centre, vert centre, wrap yes;border: bottom thin, top thin, left thin, right thin')
        title_centre_300 = xlwt.easyxf('font: height 300, name Arial, colour_index black, bold on; align: horiz centre, vert centre;border: bottom thin, top thin, left thin, right thin')
        title_left_300 = xlwt.easyxf('font: height 300, name Arial, colour_index black, bold on; align: horiz left, vert centre;border: bottom thin, top thin, left thin, right thin')
        title_left = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on; align: horiz left;')
        string_left = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz left;')
        string_right = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;')
        string_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;')
        number_centre = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz center;',num_format_str='#,##0;-#,##0')
        string_left_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz left;')
        number2d_bold = xlwt.easyxf('font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_bold_bg = xlwt.easyxf('pattern: pattern solid, fore_colour gray25;font: height 200, name Arial, colour_index black, bold on;border: bottom thin; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d_italic = xlwt.easyxf('font: height 200, name Arial, colour_index black, italic on; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        number2d = xlwt.easyxf('font: height 200, name Arial, colour_index black; align: horiz right;',num_format_str='#,##0.00;-#,##0.00')
        ws.col(1).width = 9000
        for i in range(7):
            if i != 1:
                ws.col(i).width = 4000
        ws.write_merge(0, 0, 0, 6, 'SALES RATEWISE TURNOVER', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        branch = self.env.user.branch_id
        branch_id = branch.id
        ws.write_merge(1, 1, 0, 1, 'Branch: %s'%branch.name, title_left_300)
        ws.write_merge(1, 1, 2, 6, date, title_centre_300)
        col = 2
        ws.write(col, 2, '(Value before GST)', title_centre)
        ws.write(col, 3, 'Total GST', title_centre)
        ws.write(col, 4, 'Total IGST', title_centre)
        ws.write(col, 5, 'Total CGST', title_centre)
        ws.write(col, 6, 'Total SGST', title_centre)
        
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('partner_id.vat', '!=', False),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', '=', 'posted'),
            ('branch_id', 'in', self.branch_ids.ids)
            ], order='invoice_date,name')
        amount_untaxed_5, amount_untaxed_12, amount_untaxed_18, amount_untaxed_28 = 0.0, 0.0, 0.0, 0.0
        total_cgst_25, total_cgst_6, total_cgst_9, total_cgst_14 = 0.0, 0.0, 0.0, 0.0
        total_igst_5, total_igst_12, total_igst_18, total_igst_28 = 0.0, 0.0, 0.0, 0.0
        total_amount_untaxed = 0.0
        for invoice in invoices:
            cgst_25, cgst_6, cgst_9, cgst_14 = 0.0, 0.0, 0.0, 0.0
            igst_5, igst_12, igst_18, igst_28 = 0.0, 0.0, 0.0, 0.0
            for line in invoice.invoice_line_ids:
                if line.tax_ids:
                    tax = line.tax_ids[0]
                    tax_perc = tax.amount
                        
            amount_untaxed = invoice.amount_untaxed_signed
            tax_totals = invoice.tax_totals
            amount_by_group_list = tax_totals['groups_by_subtotal'].values()
            for a in amount_by_group_list:
                for b in a:
                    tax_amount = b['tax_group_amount']
                    group = b['tax_group_name']
                    if group == 'CGST':
                        if tax_perc == 5:
                            cgst_25 = tax_amount
                            amount_untaxed_5 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        if tax_perc == 12:
                            cgst_25 = tax_amount
                            amount_untaxed_12 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 18:
                            cgst_9 = tax_amount
                            amount_untaxed_18 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 28:
                            cgst_14 = tax_amount
                            amount_untaxed_28 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                    elif group == 'IGST':
                        if tax_perc == 5:
                            igst_5 = tax_amount
                            amount_untaxed_5 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        if tax_perc == 12:
                            igst_12 = tax_amount
                            amount_untaxed_12 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 18:
                            igst_18 = tax_amount
                            amount_untaxed_18 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 28:
                            igst_28 = tax_amount
                            amount_untaxed_28 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
            
            total_cgst_25 += cgst_25
            total_cgst_6 += cgst_6
            total_cgst_9 += cgst_9
            total_cgst_14 += cgst_14
            total_igst_5 += igst_5
            total_igst_12 += igst_12
            total_igst_18 += igst_18
            total_igst_28 += igst_28
            
        
        col += 1
        ws.write(col, 0, 'B2B', string_left)
        ws.write(col, 1, '5.00%', string_right)
        ws.write(col, 2, amount_untaxed_5 or '', number2d)
        ws.write(col, 3, total_igst_5+total_cgst_25*2 or '', number2d)
        ws.write(col, 4, total_igst_5 or '', number2d)
        ws.write(col, 5, total_cgst_25 or '', number2d)
        ws.write(col, 6, total_cgst_25 or '', number2d)
        
        col += 1
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, '12.00%', string_right)
        ws.write(col, 2, amount_untaxed_12 or '', number2d)
        ws.write(col, 3, total_igst_12+total_cgst_6*2 or '', number2d)
        ws.write(col, 4, total_igst_12 or '', number2d)
        ws.write(col, 5, total_cgst_6 or '', number2d)
        ws.write(col, 6, total_cgst_6 or '', number2d)
        
        col += 1
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, '18.00%', string_right)
        ws.write(col, 2, amount_untaxed_18 or '', number2d)
        ws.write(col, 3, total_igst_18+total_cgst_9*2 or '', number2d)
        ws.write(col, 4, total_igst_18 or '', number2d)
        ws.write(col, 5, total_cgst_9 or '', number2d)
        ws.write(col, 6, total_cgst_9 or '', number2d)
        
        col += 1
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, '28.00%', string_right)
        ws.write(col, 2, amount_untaxed_28 or '', number2d)
        ws.write(col, 3, total_igst_28+total_cgst_14*2 or '', number2d)
        ws.write(col, 4, total_igst_28 or '', number2d)
        ws.write(col, 5, total_cgst_14 or '', number2d)
        ws.write(col, 6, total_cgst_14 or '', number2d)
        
        col += 1
        total_igst = total_igst_5 + total_igst_12 + total_igst_18 + total_igst_28
        total_cgst = total_cgst_25 + total_cgst_6 + total_cgst_9 + total_cgst_14
        total_gst = total_igst + total_cgst*2
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, 'Gross Sales as per GSTR1', string_right)
        ws.write(col, 2, total_amount_untaxed or '', number2d)
        ws.write(col, 3, total_gst or '', number2d)
        ws.write(col, 4, total_igst or '', number2d)
        ws.write(col, 5, total_cgst or '', number2d)
        ws.write(col, 6, total_cgst or '', number2d)
        
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('partner_id.vat', '=', False),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('state', '=', 'posted'),
            ('branch_id', '=', branch_id)
            ], order='invoice_date,name')
        amount_untaxed_5, amount_untaxed_12, amount_untaxed_18, amount_untaxed_28 = 0.0, 0.0, 0.0, 0.0
        total_cgst_25, total_cgst_6, total_cgst_9, total_cgst_14 = 0.0, 0.0, 0.0, 0.0
        total_igst_5, total_igst_12, total_igst_18, total_igst_28 = 0.0, 0.0, 0.0, 0.0
        total_amount_untaxed = 0.0
        for invoice in invoices:
            cgst_25, cgst_6, cgst_9, cgst_14 = 0.0, 0.0, 0.0, 0.0
            igst_5, igst_12, igst_18, igst_28 = 0.0, 0.0, 0.0, 0.0
            for line in invoice.invoice_line_ids:
                if line.tax_ids:
                    tax = line.tax_ids[0]
                    tax_perc = tax.amount
                        
            amount_untaxed = invoice.amount_untaxed_signed
            tax_totals = invoice.tax_totals
            amount_by_group_list = tax_totals['groups_by_subtotal'].values()
            for a in amount_by_group_list:
                for b in a:
                    tax_amount = b['tax_group_amount']
                    group = b['tax_group_name']
                    if group == 'CGST':
                        if tax_perc == 5:
                            cgst_25 = tax_amount
                            amount_untaxed_5 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        if tax_perc == 12:
                            cgst_25 = tax_amount
                            amount_untaxed_12 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 18:
                            cgst_9 = tax_amount
                            amount_untaxed_18 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 28:
                            cgst_14 = tax_amount
                            amount_untaxed_28 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                    elif group == 'IGST':
                        if tax_perc == 5:
                            igst_5 = tax_amount
                            amount_untaxed_5 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        if tax_perc == 12:
                            igst_12 = tax_amount
                            amount_untaxed_12 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 18:
                            igst_18 = tax_amount
                            amount_untaxed_18 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
                        elif tax_perc == 28:
                            igst_28 = tax_amount
                            amount_untaxed_28 += amount_untaxed
                            total_amount_untaxed += amount_untaxed
            
            total_cgst_25 += cgst_25
            total_cgst_6 += cgst_6
            total_cgst_9 += cgst_9
            total_cgst_14 += cgst_14
            total_igst_5 += igst_5
            total_igst_12 += igst_12
            total_igst_18 += igst_18
            total_igst_28 += igst_28
            
        col += 3
        ws.write(col, 0, 'B2C', string_left)
        ws.write(col, 1, '5.00%', string_right)
        ws.write(col, 2, amount_untaxed_5 or '', number2d)
        ws.write(col, 3, total_igst_5+total_cgst_25*2 or '', number2d)
        ws.write(col, 4, total_igst_5 or '', number2d)
        ws.write(col, 5, total_cgst_25 or '', number2d)
        ws.write(col, 6, total_cgst_25 or '', number2d)
        
        col += 1
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, '12.00%', string_right)
        ws.write(col, 2, amount_untaxed_12 or '', number2d)
        ws.write(col, 3, total_igst_12+total_cgst_6*2 or '', number2d)
        ws.write(col, 4, total_igst_12 or '', number2d)
        ws.write(col, 5, total_cgst_6 or '', number2d)
        ws.write(col, 6, total_cgst_6 or '', number2d)
        
        col += 1
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, '18.00%', string_right)
        ws.write(col, 2, amount_untaxed_18 or '', number2d)
        ws.write(col, 3, total_igst_18+total_cgst_9*2 or '', number2d)
        ws.write(col, 4, total_igst_18 or '', number2d)
        ws.write(col, 5, total_cgst_9 or '', number2d)
        ws.write(col, 6, total_cgst_9 or '', number2d)
        
        col += 1
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, '28.00%', string_right)
        ws.write(col, 2, amount_untaxed_28 or '', number2d)
        ws.write(col, 3, total_igst_28+total_cgst_14*2 or '', number2d)
        ws.write(col, 4, total_igst_28 or '', number2d)
        ws.write(col, 5, total_cgst_14 or '', number2d)
        ws.write(col, 6, total_cgst_14 or '', number2d)
        
        col += 1
        total_igst = total_igst_5 + total_igst_12 + total_igst_18 + total_igst_28
        total_cgst = total_cgst_25 + total_cgst_6 + total_cgst_9 + total_cgst_14
        total_gst = total_igst + total_cgst*2
        ws.write(col, 0, '', string_left)
        ws.write(col, 1, 'Gross Sales as per GSTR1', string_right)
        ws.write(col, 2, total_amount_untaxed or '', number2d)
        ws.write(col, 3, total_gst or '', number2d)
        ws.write(col, 4, total_igst or '', number2d)
        ws.write(col, 5, total_cgst or '', number2d)
        ws.write(col, 6, total_cgst or '', number2d)
        
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'SALES RATEWISE TURNOVER.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/sales/register?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }