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
         
class PurchaseRegister(models.TransientModel):
    _name = 'purchase.register'
    _description = 'Purchase Register' 

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    branch_ids = fields.Many2many('res.branch', string='Branches')
    report_file = fields.Binary('Report File', attachment=True)
    report_file_name = fields.Char('Report File Name')
    
    @api.model
    def default_get(self, default_fields):
        res = super(PurchaseRegister, self).default_get(default_fields)
        res.update({'branch_ids' : self._context.get('allowed_branch_ids', self.env.user.branch_ids.ids)})
        return res
    
    def action_print(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Purchase Register')
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
        for i in range(0, 20):
            if i != 1:
                ws.col(i).width = 4000
        ws.write_merge(0, 1, 0, 19, 'Purchase Register', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(2, 3, 0, 19, date, title_left_bg)
        ws.write(4, 0, 'Date', title_centre)
        ws.write(4, 1, 'Particulars', title_centre)
        ws.write(4, 2, 'Voucher Type', title_centre)
        ws.write(4, 3, 'Voucher Number', title_centre)
        ws.write(4, 4, 'Supplier Invoice No.', title_centre)
        ws.write(4, 5, 'Supplier Invoice Date', title_centre)
        ws.write(4, 6, 'GSTIN/UIN', title_centre)
        ws.write(4, 7, 'Quantity', title_centre)
        ws.write(4, 8, 'Value', title_centre)
        ws.write(4, 9, 'Addl. Cost', title_centre)
        ws.write(4, 10, 'Gross Total', title_centre)
        ws.write(4, 11, 'IGST Input', title_centre)
        ws.write(4, 12, 'CGST Input', title_centre)
        ws.write(4, 13, 'SGST Input', title_centre)
        ws.write(4, 14, 'TDS - Purchase (194Q)', title_centre)
        ws.write(4, 15, 'Round Off', title_centre)
        ws.write(4, 16, 'Status', title_centre)
        col = 5
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('state', '=', 'posted'),
            ('branch_id', 'in', self.branch_ids.ids)
            ], order='date,name')
        total_cgst, total_sgst, total_igst = 0.0, 0.0, 0.0
        total_round_off, total_amount_taxed = 0.0, 0.0
        total_amount_untaxed, total_qty, total_tds = 0.0, 0.0, 0.0
        total_add_cost = 0
        for invoice in invoices:
            sgst, cgst = 0.0, 0.0
            igst, round_off = 0.0, 0.0
            qty, tds, add_cost = 0, 0, 0
            sign = 1
            
            if invoice.state == 'cancel':
                ws.write(col, 0, invoice.date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Purchase Bill', string_left)
                ws.write(col, 3, invoice.name, string_left)
                ws.write(col, 4, invoice.ref or '', string_left)
                ws.write(col, 5, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 6, invoice.partner_id.vat or '', string_left)
                ws.write(col, 7, '', number2d)
                ws.write(col, 8, '', number2d)
                ws.write(col, 9, '', number2d)
                ws.write(col, 10, '', number2d)
                ws.write(col, 11, '', number2d)
                ws.write(col, 12, '', number2d)
                ws.write(col, 13, '', number2d)
                ws.write(col, 14, '', number2d)
                ws.write(col, 15, '', number2d)
                ws.write(col, 16, 'CANCELLED', string_left)
                col += 1
            else:
                rounding_line = invoice.line_ids.filtered(lambda l: l.display_type == 'rounding')
                
                if rounding_line:
                    round_off = sign*-1*rounding_line.balance
                    
                amount_untaxed = 0.0
                amount_total = invoice.amount_total_signed
                tax_totals = invoice.tax_totals
                for x in tax_totals['groups_by_subtotal']['Untaxed Amount']:
                    if x['tax_group_name'] == 'SGST':
                        sgst = x['tax_group_amount']
                    elif x['tax_group_name'] == 'CGST':
                        cgst = x['tax_group_amount']
                    elif x['tax_group_name'] == 'IGST':
                        igst = x['tax_group_amount']
                    elif x['tax_group_name'] == 'TDS':
                        tds = x['tax_group_amount']
                if invoice.move_type == 'in_invoice':
                    amount_total = amount_total * -1
                for line in invoice.invoice_line_ids:
                    if line.product_id:
                        amount_untaxed += sign*line.price_subtotal
                    else:
                        if line.account_id and line.account_id.name == 'Round Off D':
                            round_off += line.price_subtotal
                        else:
                            add_cost += line.price_subtotal
                    qty += sign*line.quantity
                    total_qty += qty
                
                total_cgst += cgst
                total_sgst += sgst
                total_igst += igst
                total_tds += tds
                total_add_cost += add_cost
                total_round_off += round_off
                total_amount_untaxed += amount_untaxed
                total_amount_taxed += amount_total
                
                ws.write(col, 0, invoice.date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Purchase Bill', string_left)
                ws.write(col, 3, invoice.name, string_left)
                ws.write(col, 4, invoice.ref or '', string_left)
                ws.write(col, 5, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 6, invoice.partner_id.vat or '', string_left)
                ws.write(col, 7, qty or '', number2d)
                ws.write(col, 8, amount_untaxed, number2d)
                ws.write(col, 9, add_cost or '', number2d)
                ws.write(col, 10, amount_total, number2d)
                ws.write(col, 11, igst or '', number2d)
                ws.write(col, 12, cgst or '', number2d)
                ws.write(col, 13, sgst or '', number2d)
                ws.write(col, 14, tds or '', number2d)
                ws.write(col, 15, round_off or '', number2d)
                col += 1
        ws.write(col, 7, total_qty or '', number2d_bold_bg)
        ws.write(col, 8, total_amount_untaxed or '', number2d_bold_bg)
        ws.write(col, 9, total_add_cost or '', number2d_bold_bg)
        ws.write(col, 10, total_amount_taxed or '', number2d_bold_bg)
        ws.write(col, 11, total_igst or '', number2d_bold_bg)
        ws.write(col, 12, total_cgst or '', number2d_bold_bg)
        ws.write(col, 13, total_sgst or '', number2d_bold_bg)
        ws.write(col, 14, total_tds or '', number2d_bold_bg)
        ws.write(col, 15, total_round_off or '', number2d_bold_bg)
        fd = BytesIO()
        wb.save(fd)
        fd.seek(0)
        out = base64.encodebytes(fd.getvalue())
        fd.close()
        self.write({'report_file': out, 'report_file_name': 'Purchase Register.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/purchase/register?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    
    def action_print_dn(self):
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Debit Note Register')
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
        for i in range(0, 21):
            if i != 1:
                ws.col(i).width = 4000
        ws.write_merge(0, 0, 0, 20, 'Debit Note Register', title_centre_300)
        date = self.start_date.strftime('%d-%m-%Y') + ' To ' + self.end_date.strftime('%d-%m-%Y') 
        ws.write_merge(1, 1, 0, 20, date, title_left_bg)
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
            ('move_type', '=', 'in_refund'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('state', '!=', 'draft'),
            ('branch_id', 'in', self.branch_ids.ids)
            ], order='date,name')
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
            if invoice.state == 'cancel':
                ws.write(col, 0, invoice.invoice_date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Debit Note', string_left)
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
                sales_account = 0.0
                group, tcs = False, False
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
                
                ws.write(col, 0, invoice.date.strftime('%d-%m-%Y'), string_left)
                ws.write(col, 1, invoice.partner_id.name, string_left)
                ws.write(col, 2, 'Debit Note', string_left)
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
        self.write({'report_file': out, 'report_file_name': 'Debit Note Register.xls'})
        return {
             'type' : 'ir.actions.act_url',
             'url': '/purchase/register?id=%s&filename=%s'%(self.id, self.report_file_name),
             'target': 'new',
             }
    