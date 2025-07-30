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

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from io import StringIO, BytesIO
import csv
import base64
from datetime import datetime
import logging
logger = logging.getLogger('Data Clearing:')
import pytz

class Company(models.Model):
    _inherit = 'res.company'
    
    def _autorise_lock_date_changes(self, vals):
        return True
        
    factory_picking_out_id = fields.Many2one('stock.picking.type', 'Factory Picking Out')
    factory_git_picking_id = fields.Many2one('stock.picking.type', 'Factory GIT')
    git_location_id = fields.Many2one('stock.location', 'GIT Location')
    discount_product_id = fields.Many2one('product.product', 'Discount Product')
    factory_rmgit_id = fields.Many2one('stock.picking.type', 'Factory RM->GIT')
    factory_gitwip_id = fields.Many2one('stock.picking.type', 'Factory GIT->WIP')
    factory_wipreject_id = fields.Many2one('stock.picking.type', 'Factory WIP->Rejection Area')
    factory_qcreject_id = fields.Many2one('stock.picking.type', 'Factory GRN->Rejection Area')
    cn_journal_id = fields.Many2one('account.journal', 'CN Journal')
    dn_journal_id = fields.Many2one('account.journal', 'DN Journal')
    branch_acc_id = fields.Many2one('account.account', 'Branch Consignment Account')
    branch_journal_id = fields.Many2one('account.journal', 'Branch Adjustment Journal')
    
    data_file = fields.Binary('Data File')
    data_file_name = fields.Char('Data File Name')
    data_file1 = fields.Binary('SN File')
    data_file_name1 = fields.Char('Data File Name1')
    new_pricelist_id = fields.Many2one('product.pricelist', 'Pricelist')
    inv_location_id = fields.Many2one('stock.location', 'Src Location')
    inv_location_dest_id = fields.Many2one('stock.location', 'Destination Location')
    unbuild_location_id = fields.Many2one('stock.location', 'Unbuild Location')
    ob_journal_id = fields.Many2one('account.journal', 'OB Journal')
    ho_branch_id = fields.Many2one('res.branch', 'HO Branch')
    stock_branch_id = fields.Many2one('res.branch', 'Branch2')
    stock_location_dest_id = fields.Many2one('stock.location', 'Stock Location')
    inv_branch_id = fields.Many2one('res.branch', 'Branch')
    suspense_account_id = fields.Many2one('account.account', 'Suspense Account')
    inv_date = fields.Date('Inventory Date')
    loose_ok = fields.Boolean('Loose Stock')
    error_details = fields.Text('Error Details')
    sns = fields.Text('SNS')
    product_categ_id = fields.Many2one('product.category', 'Product Category')
    
    correction_journal_id = fields.Many2one('account.journal', 'Journal')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    clear_model_id = fields.Many2one('ir.model', 'Data Model')
    data_count = fields.Integer('Data Count')
    branch_soprice_ok = fields.Boolean('Branch SO Price')
    correction_date = fields.Datetime('Correction Date')
    location_id1 = fields.Many2one('stock.location', 'From Location')
    location_id2 = fields.Many2one('stock.location', 'To Location')

    def action_clear_data(self):
        table_name = self.clear_model_id.model.replace('.', '_')
        if table_name == 'account_move':
            logger.info('-'*75)
            self.env.cr.execute("""select count(*) from %s where journal_id=%s"""%(table_name, self.correction_journal_id.id))
            result = self.env.cr.dictfetchall()
            logger.info('Start:%s-->%s'%(self.clear_model_id.name, result[0]['count']))
            
            self.env.cr.execute("""select move_id from account_move_line""")
            result = self.env.cr.dictfetchall()
            move_ids = []
            for res in result:
                move_ids.append(res['move_id'])
            move_ids = list(set(move_ids))
            
            self.env.cr.execute("""select id from account_move""")
            result = self.env.cr.dictfetchall()
            move_ids2 = []
            for res in result:
                move_ids2.append(res['id'])
            move_ids3 = []
            if move_ids:
                for move_id2 in move_ids2:
                    if move_id2 not in move_ids:
                        move_ids3.append(move_id2)
            count = 1
            move_ids3 = list(set(move_ids3))
            move_ids3_count = len(move_ids3)
            if move_ids3_count > 5000:
                move_ids3 = move_ids3[:5000]
            for move_id3 in move_ids3:
                logger.info('Deleting:%s/%s'%(count, move_ids3_count))
                self.env.cr.execute("""delete from account_move where id=%s"""%(move_id3))
                count += 1
            # self.env.cr.execute("""
            #     delete from %s 
            #     where id in (select id from %s where journal_id=%s limit %s)
            #     """%(table_name, table_name, self.correction_journal_id.id, self.data_count))
            
            self.env.cr.execute("""select id from %s where journal_id=%s limit %s"""%(table_name, self.correction_journal_id.id, self.data_count))
            result = [res['id'] for res in self.env.cr.dictfetchall()]
            count = 1
            tc = len(result)
            for res_id in result:
                self.env.cr.execute("""delete from %s where id=%s"""%(table_name, res_id))
                logger.info('Deleting:%s-%s/%s'%(self.clear_model_id.name, count, tc))
                count += 1
                
            self.env.cr.execute("""select count(*) from %s where journal_id=%s"""%(table_name, self.correction_journal_id.id))
            result = self.env.cr.dictfetchall()
            logger.info('Stop:%s-->%s'%(self.clear_model_id.name, result[0]['count']))
            logger.info('-'*75)
        else:
            logger.info('-'*75)
            self.env.cr.execute("""select count(*) from %s"""%(table_name))
            result = self.env.cr.dictfetchall()
            logger.info('Start:%s-->%s'%(self.clear_model_id.name, result[0]['count']))
            
            # self.env.cr.execute("""
            #     delete from %s 
            #     where id in (select id from %s limit %s)
            #     """%(table_name, table_name, self.data_count))
            
            self.env.cr.execute("""select id from %s limit %s"""%(table_name, self.data_count))
            result = [res['id'] for res in self.env.cr.dictfetchall()]
            count = 1
            tc = len(result)
            for res_id in result:
                self.env.cr.execute("""delete from %s where id=%s"""%(table_name, res_id))
                logger.info('Deleting:%s-%s/%s'%(self.clear_model_id.name, count, tc))
                count += 1
            self.env.cr.execute("""select count(*) from %s"""%(table_name))
            result = self.env.cr.dictfetchall()
            logger.info('End:%s-->%s'%(self.clear_model_id.name, result[0]['count']))
            logger.info('-'*75)
        return True
    
    def _login_user(self):
        for company in self:
            company.login_user_id = self.env.user.user_access and self.env.user.id or False
    
    # def action_inventory_adjustment(self):
    #     file_data = self.read_csv_file()
    #     print(file_data)
    #     missing_products = []
    #     products_dic = {}
    #     product_obj = self.env['product.product']
    #     products = product_obj.search([])
    #     for product in products:
    #         if product.default_code:
    #             products_dic.update({product.default_code: product})
    #     for data in file_data:
    #         if data['Internal Reference'] not in products_dic:
    #             missing_products.append(data['Internal Reference'])
    #     if missing_products:
    #         raise UserError('Missing Products:\n'+str(list(set(missing_products))))
    #     lot_dic = {}
    #     lot_obj = self.env['stock.lot']
    #     move_vals_dic = {}
    #     products_qty_dic = {}
    #     products_date_dic = {}
    #     file_data = self.read_csv_file()
    #     return True
    
    def update_so_invoices(self):
        for order in self.env['sale.order'].with_context(no_filter=True).search([]):
            for invoice in order.invoice_ids:
                invoice.so_id = order.id
        return True
    
    def update_jvs(self):
        for move in self.env['account.move'].search([('move_type', '=', 'out_invoice')]):
            if move.amount_total == 0:
                move.recompute = not move.recompute 
        return True
        
    def update_payment_accounts(self):
        payments = self.env['account.payment'].with_context(no_filter=True).search([('state', '=', 'posted')])
        for payment in payments:
            journal = payment.journal_id
            in_account_id = journal.inbound_payment_method_line_ids[0].payment_account_id.id
            out_account_id = journal.outbound_payment_method_line_ids[0].payment_account_id.id
            for line in payment.line_ids:
                if line.account_id.id == journal.default_account_id.id:
                    if line.debit > 0:
                        line.account_id = in_account_id
                    elif line.credit > 0:
                        line.account_id = out_account_id
        return True
    
    def update_invoice_value(self):
        invoices = self.env['account.move'].search([
            ('move_type', 'in', ('out_invoice', 'out_refund'))
            ])
        for invoice in invoices:
            if invoice.amount_total == 0:
                invoice.recompute = not invoice.recompute 
        return True
    
    def action_update_tag(self):
        orders = self.env['sale.order'].with_context(no_filter=True).search([('tag_id', '!=', False)])
        partner_dic = {}
        for order in orders:
            if not order.partner_id in partner_dic:
                partner_dic.update({order.partner_id: order.tag_id.id})
        for partner in partner_dic:
            partner.write({'tag_id': partner_dic[partner]})
        return True
    
    def action_brs_correction(self):
        payment_obj = self.env['account.payment']
        vendor_payments = payment_obj.search([('state', '=', 'posted')])
        for vendor_payment in vendor_payments:
            if vendor_payment.journal_id:
                pass
        return True
    
    def action_clear_stock(self):
        quants = self.env['stock.quant'].with_context(no_filter=True).search([
            ('branch_id', '=', self.stock_branch_id.id),
            ('location_id', '=', self.stock_location_dest_id.id)
            ])
        sns = self.env['stock.serial'].search([])
        for sn in sns:
            if sn.quantity > 0:
                line = sn.line_ids[0]
                qty = round(line.quantity, 2)
                sn.line_ids[0].quantity = qty
                ssl_vals = {
                    'serial_id': sn.id,
                    'location_id': line.location_dest_id.id,
                    'location_dest_id': self.inv_location_id.id,
                    'quantity': qty,
                    'date': fields.Datetime.now()
                    }
                self.env['stock.serial.line'].create(ssl_vals)
        for quant in quants:
            # self.env.cr.execute("""delete from stock_quant where id=%s"""%(quant.id))
            # quant.unlink()
            quant.reserved_quantity = quant.quantity
            # smls = self.env['stock.move.line'].search([
            #     ('product_id', '=', quant.product_id.id),
            #     ('location_dest_id', '=', quant.location_id.id)
            #     ])
            # res_qty = 0
            # for sml in smls:
            #     res_qty += sml.reserved_qty
            # if quant.reserved_quantity < res_qty:
            #     quant.reserved_quantity = res_qty
            quant.inventory_quantity = 0
            quant.action_apply_inventory()
            quant.reserved_quantity = 0
        # smls = self.env['stock.move.line'].with_context(no_filter=True).search([
        #     ('branch_id', '=', self.stock_branch_id.id),
        #     ('product_category_name', '=', self.product_categ_id.complete_name)
        #     ])
        # if smls:
        #     for sml in smls:
        #         self.env.cr.execute("""delete from stock_move_line where id=%s"""%(sml.id))
        # svls = self.env['stock.valuation.layer'].with_context(no_filter=True).search([
        #     ('branch_id', '=', self.stock_branch_id.id),
        #     ('product_categ_id', '=', self.product_categ_id.id)
        #     ])
        # for svl in svls:
        #     if svl.account_move_id:
        #         svl.account_move_id.button_draft()
        #         svl.account_move_id.unlink()
        #     self.env.cr.execute("""delete from stock_valuation_layer where id=%s"""%(svl.id))
        #     # svl.unlink()
        # ss_ids = self.env['stock.serial'].search([('product_id.categ_id', '=', self.product_categ_id.id)]).ids
        # psl_ids = self.env['picking.serial.line'].search([('serial_id', 'in', ss_ids)]).ids
        # for psl_id in psl_ids:
        #     self.env.cr.execute("""delete from picking_serial_line where id=%s"""%(psl_id))
        # ssl_ids = self.env['stock.serial.line'].search([('serial_id', 'in', ss_ids)]).ids
        # for ssl_id in ssl_ids:
        #     self.env.cr.execute("""delete from stock_serial_line where id=%s"""%(ssl_id))
        # for ss_id in ss_ids:
        #     self.env.cr.execute("""delete from stock_serial where id=%s"""%(ss_id))
        return True
    
    def update_product_cost(self):
        file_data = self.read_csv_file()
        cost_dic = {}
        for data in file_data:
            cost_dic.update({data['Code']: data['Cost']})
        for product in self.env['product.template'].search([]):
            if product.default_code in cost_dic:
                product.standard_price = cost_dic[product.default_code]
                
        return True
    
    def update_slnos(self):
        file_data = self.read_csv_file()
        product_dic = {}
        for product in self.env['product.product'].search([]):
            if product.default_code:
                product_dic.update({product.default_code: product.id})
        cost_dic = {}
        sl_number_list = []
        for data in file_data:
            if data['Code'] and data['Serial Number'] and data['Lot Number']:
                product_id = product_dic.get(data['Code'], False)
                if product_id:
                    sl_numbers = self.env['stock.serial'].with_context(no_filter=True).search([
                        ('name', '=', data['Serial Number']),
                        ('product_id', '=', product_id),
                        ('lot_id.name', '=', data['Lot Number'])
                        ])
                    if sl_numbers:
                        sl_number_list.append(sl_numbers[0])

        count = 1
        total_count = len(sl_number_list)
        logger.info('%s'%sl_number_list)
        logger.info('%s'%total_count)
        for sl_number in sl_number_list:
            logger.info('%s/%s'%(count, total_count))
            sl_number.action_slnqty_correction()
            count += 1
        return True
    
    def action_clear_serial_numbers(self):

        if not self.correction_date:
            raise UserError('Enter Correction Date.')
        file_data = self.read_csv_file()
        product_dic = {}
        for product in self.env['product.product'].search([]):
            if product.default_code:
                product_dic.update({product.default_code: product.id})
        cost_dic = {}
        sl_number_list = []
        for data in file_data:
            if data['Code'] and data['Serial Number'] and data['Lot Number']:
                product_id = product_dic.get(data['Code'], False)
                if product_id:
                    sl_numbers = self.env['stock.serial'].with_context(no_filter=True).search([
                        ('name', '=', data['Serial Number']),
                        ('product_id', '=', product_id),
                        ('lot_id.name', '=', data['Lot Number'])
                        ])
                    if sl_numbers:
                        sl_number_list.append(sl_numbers[0])
                    
        count = 1
        total_count = len(sl_number_list)
        logger.info('%s'%sl_number_list)
        for sl in sl_number_list:
            sl.action_clear_location_date(self.location_id1.id, self.location_id2.id, self.correction_date)
        return True

    def update_svl_cost(self):
        file_data = self.read_csv_file()
        cost_dic = {}
        unit_cost_dic = {}
        for data in file_data:
            cost_dic.update({data['Code']: data['Cost']})
        for product in self.env['product.product'].search([]):
            if product.default_code in cost_dic:
                unit_cost_dic.update({product.id: cost_dic[product.default_code]})
        svl_obj = self.env['stock.valuation.layer']
        for product_id in unit_cost_dic:
            svls = svl_obj.with_context(no_filter=True).search([
                ('product_id', '=', product_id),
                ('branch_id', '=', 16)
                ])
            for svl in svls:
                unit_cost = round(float(unit_cost_dic[product_id]), 2)
                svl.write({'unit_cost': unit_cost, 'value': round(unit_cost*svl.quantity, 3)})
                # if not svl.account_move_id:
                #     svl.with_context(branch_id=svl.branch_id.id).create_svl_jv()
                if svl.stock_move_id:
                    svl.stock_move_id.price_unit = unit_cost
            
        return True
    
    def read_csv_file(self):
        import_file = BytesIO(base64.decodebytes(self.data_file))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=',')
        return reader
    
    def read_csv_file1(self):
        import_file = BytesIO(base64.decodebytes(self.data_file1))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=',')
        return reader
    
    def read_csv_file2(self):
        import_file = BytesIO(base64.decodebytes(self.data_file))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=';')
        return reader
    
    def action_fetch_sns(self):
        file_data = self.read_csv_file1()
        sns = []
        ctx = dict(self.env.context or {})
        ctx['no_filter'] = True
        for data in file_data:
            if data['Serial Number']:
                sns.append(data['Serial Number'].replace("\n", ""))
        self.sns = sns
        if sns:
            action = self.env['ir.actions.act_window']._for_xml_id('etl_stock.action_stock_serials')
            action['domain'] = [('name', 'in', sns)]
            action['context'] = ctx
            # action = {
            #     'name': 'Serial Numbers',
            #     'context': ctx,
            #     'view_mode': 'list',
            #     'view_id': self.env.ref('etl_stock.view_stock_serial_tree').id,
            #     'res_model': 'stock.serial',
            #     'type': 'ir.actions.act_window',
            #     'domain': [('name', 'in', sns)],
            #     }
            return action
        return True
        
    def update_location_branch(self):
        moves = self.env['stock.move'].search([('date', '>=', '2024-01-14'), ('date', '<', '2024-01-15')])
        for move in moves:
            move.write({'location_dest_id': self.inv_location_dest_id.id, 'branch_id': self.inv_branch_id.id})
            for ml in move.move_line_ids:
                ml.location_dest_id = self.inv_location_dest_id.id
                if ml.lot_id:
                    for serial in ml.lot_id.serial_ids:
                        if serial.name:
                            serial.line_ids.location_dest_id = self.inv_location_dest_id.id
                        else:
                            serial.unlink() 
        return True
    
    def update_bom(self):
        file_data = self.read_csv_file()
        codes = []
        bom_obj = self.env['mrp.bom']
        bom_line_obj = self.env['mrp.bom.line']
        product_obj = self.env['product.product']
        products_dic = {}
        wc_dic = {}
        wcs = []
        for data in file_data:
            code = data.get('Code', '')
            bom_code = data.get('BOM Code', '')
            if code:
                codes.append(code)
            if bom_code:
                codes.append(bom_code)
            wc = data['WC']
        codes = list(set(codes))
        products = product_obj.search([('default_code', 'in', codes)])
        for product in products:
            products_dic.update({product.default_code: product})
        file_data = self.read_csv_file()
        missing_data = ''
        for data in file_data:
            code = data.get('Code', '')
            bom_code = data.get('BOM Code', '')
            wc = data['WC']
            if code and bom_code:
                if code in products_dic:
                    pass
                else:
                    bom_id = False
            if code or bom_code:
                qty = data.get('Quantity', 1) or 0
                qty = round(float(qty), 3)
                bom_qty = data.get('BOM Qty', 1)
                bom_qty = round(float(bom_qty), 3)
                if code and code in products_dic:
                    bom_id = bom_obj.create({
                        'product_tmpl_id': products_dic[code].product_tmpl_id.id,
                        'product_uom_id': products_dic[code].product_tmpl_id.uom_id.id,
                        'product_qty': qty
                        }).id
                if bom_id and bom_code and bom_code in products_dic:
                    bom_line_id = bom_line_obj.create({
                        'bom_id': bom_id,
                        'product_id': products_dic[bom_code].id,
                        'product_uom_id': products_dic[bom_code].product_tmpl_id.uom_id.id,
                        'product_qty': bom_qty
                        })
                if bom_id and wc:
                    if wc in wc_dic:
                        workcenter_id = wc_dic[wc]
                    else:
                        wcs = self.env['mrp.workcenter'].search([('name', '=', wc)])
                        if wcs:
                            workcenter_id = wcs[0].id
                            wc_dic.update({wc: workcenter_id})
                        else:
                            workcenter_id = self.env['mrp.workcenter'].create({'name': wc}).id
                            wc_dic.update({wc: workcenter_id})
                    self.env['mrp.routing.workcenter'].create({
                        'name': wc,
                        'workcenter_id': workcenter_id,
                        'bom_id': bom_id
                        })
            else:
                missing_data += code + '\n'
        self.error_details = missing_data
        return True
    
    def update_coa(self):
        file_data = self.read_csv_file2()
        account_obj = self.env['account.account']
        codes = []
        account_dic = {}
        for data in file_data:
            if data['Code']:
                codes.append(data['Code'])
        codes = list(set(codes))
        accounts = account_obj.search([])
        for account in accounts:
            account_dic.update({account.code: account})
        missing_accounts = []
        for code in codes:
            if code not in account_dic:
                missing_accounts.append(code)
        if missing_accounts:
            raise UserError('%s is missing'%missing_accounts)
        file_data = self.read_csv_file2()
        lines = []
        total_debit = 0.00
        total_credit = 0.00
        journal_id = self.ob_journal_id.id
        for data in file_data:
            if not data['Code']:
                continue
            if data['Debit'] and float(data['Debit']) > 0:
                total_debit += float(data['Debit'])
                debit_line_vals = {
                    'account_id': account_dic[data['Code']].id,
                    'debit': float(data['Debit']),
                    'credit': 0,
                    'journal_id': journal_id,
                    }
                lines.append((0, 0, debit_line_vals))
            if data['Credit'] and float(data['Credit']) > 0:
                total_credit += float(data['Credit'])
                credit_line_vals = {
                    'account_id': account_dic[data['Code']].id,
                    'debit': 0,
                    'credit': float(data['Credit']),
                    'journal_id': journal_id,
                    }
                lines.append((0, 0, credit_line_vals))
        if total_credit != total_debit:
            if total_credit > total_debit:
                debit_value = total_credit - total_debit
                debit_line_vals = {
                    'account_id': self.suspense_account_id.id,
                    'debit': debit_value,
                    'credit': 0,
                    'journal_id': journal_id,
                    }
                lines.append((0, 0, debit_line_vals))
                
            else:
                credit_value = total_debit - total_credit
                credit_line_vals = {
                    'account_id': self.suspense_account_id.id,
                    'debit': 0,
                    'credit': credit_value,
                    'journal_id': journal_id,
                    }
                lines.append((0, 0, credit_line_vals))
        move_obj = self.env['account.move']
        move_name_prefix = 'OB/2425/%s/'%(self.inv_branch_id.code)
        obs = move_obj.search([
            ('journal_id', '=', journal_id),
            ('branch_id', '=', self.inv_branch_id.id),
            ('move_name', 'ilike', move_name_prefix)
            ])
        obs_count = 0
        if obs:
            obs_count = len(obs.ids)
        move_name = '%s%s'%(move_name_prefix, str(obs_count+1).zfill(6))
        move_vals = {
            'journal_id': journal_id,
            'name': '/',
            'move_name': move_name,
            'branch_id': self.inv_branch_id.id,
            'line_ids': lines,
            'date': '2024-09-30',
            'posted_before': True
            }
        move = move_obj.create(move_vals)
        move.action_post()
        return True
    
    def update_cost(self):
        file_data = self.read_csv_file()
        product_obj = self.env['product.product']
        products = product_obj.search([])
        products_dic = {}
        for product in products:
            if product.default_code:
                products_dic.update({product.default_code: product})
        for data in file_data:
            code = data['Internal Reference']
            if data['Cost'] and code:
                cost = float(data['Cost'].replace(',', ''))
                if cost > 0 and code in products_dic:
                    products_dic[code].write({'standard_price': cost})
        return True
    
    def update_payables(self):
        file_data = self.read_csv_file()
        partner_obj = self.env['res.partner']
        for data in file_data:
            if data['Bill Number'] and data['Date']:
                partners = partner_obj.search([('partner_code', '=', data['Partner Code'])])
                date = data['Date']
                print(partners,date)
        return True
    
    def update_customer_account(self):
        acc_dic = {
            'Trade Receivables - Open Market': 5007,
            'Trade Receivables - Export': 5006,
            'Trade Receivables - RTC': 5009,
            'Trade receivables - Tyre Management': 5008
            }
        partners = self.env['res.partner'].search([('customer_rank', '>', 0)])
        partner_dic = {}
        for partner in partners:
            if partner.sfa_code:
                partner_dic.update({partner.sfa_code: partner})
        file_data = self.read_csv_file()
        for data in file_data:
            if data['Sale/Reference'] in partner_dic:
                partner = partner_dic[data['Sale/Reference']]
                partner.property_account_receivable_id = acc_dic[data['Accounts Receivable']]
        return True
    
    def upload_ob_rec(self):
        file_data = self.read_csv_file()
        self.env.cr.execute("""select name from account_move""")
        ref_list = [ref['name'] for ref in self.env.cr.dictfetchall()]
        for data in file_data:
            if data['Bill Number'] in ref_list:
                raise UserError('%s is duplicated'%data['Bill Number'])
            else:
                ref_list.append(data['Bill Number'])
        if not self.inv_branch_id:
            raise UserError('Enter Branch')
        move_obj = self.env['account.move']
        partner_dic = {}
        partner_obj = self.env['res.partner']
        partners = partner_obj.search([])
        for partner in partners:
            if partner.partner_code:
                partner_dic.update({partner.partner_code: partner})
        file_data = self.read_csv_file()
        journal_id = self.ob_journal_id.id
        for data in file_data:
            number = data['Bill Number']
            if data['Partner Code'] in partner_dic:
                partner = partner_dic[data['Partner Code']]
            lines = []
            if data['DEBIT'] and float(data['DEBIT']) > 0:
                amount = float(data['DEBIT'])
                debit_line = {
                    'partner_id': partner.id,
                    'account_id': partner.property_account_receivable_id.id,
                    'debit': amount,
                    'credit': 0,
                    'journal_id': journal_id,
                    'name': number,
                    }
                credit_line = {
                    'account_id': self.suspense_account_id.id,
                    'debit': 0,
                    'credit': amount,
                    'journal_id': journal_id,
                    'name': number,
                    }
                lines.append((0, 0, debit_line))
                lines.append((0, 0, credit_line))
            if data['CREDIT'] and float(data['CREDIT']) > 0:
                amount = float(data['CREDIT'])
                debit_line = {
                    'account_id': self.suspense_account_id.id,
                    'debit': amount,
                    'credit': 0,
                    'journal_id': journal_id,
                    'name': number,
                    }
                credit_line = {
                    'account_id': partner.property_account_receivable_id.id,
                    'debit': 0,
                    'credit': amount,
                    'journal_id': journal_id,
                    'partner_id': partner.id,
                    'name': number,
                    }
                lines.append((0, 0, debit_line))
                lines.append((0, 0, credit_line))
            date = datetime.strptime(data['Date'], "%d/%m/%Y")
            if lines:
                move_vals = {
                'journal_id': journal_id,
                'name': number,
                'move_name': number,
                'branch_id': self.inv_branch_id.id,
                'line_ids': lines,
                'date': date,
                'posted_before': True,
                'ref': 'OB-AR'
                }
                move = move_obj.create(move_vals)
                move.action_post()
        self.inv_branch_id = False
        return True
    
    def upload_vendor_payable(self):
        file_data = self.read_csv_file()
        partner_obj = self.env['res.partner']
        file_data = self.read_csv_file()
        accounts = self.env['account.account'].search([])
        acc_dic = {}
        for account in accounts:
            acc_dic.update({account.code: account.id})
        
        acc_emp_dic = {}
        
        # mtv_obj = self.env['mail.tracking.value']
        # mtvs = mtv_obj.search([('new_value_integer', '=', 5649)])
        # for mtv in mtvs:
        #     print(mtv.mail_message_id,mtv.mail_message_id.res_id)
        #     move_obj = self.env['account.move']
        #     move = move_obj.browse(mtv.mail_message_id.res_id)
        #     print(move.name,move.write_date)
        for data in file_data:
            if data['GL Code'] and data['Partner Code']:
                acc_emp_dic.update({data['GL Code']: data['Partner Code']})
        print(acc_emp_dic)
        #         partner = partner_obj.search([
        #             ('partner_code', '=', data['Partner Code'])
        #             ], limit=1)
        #         if partner:
        #             lines = self.env['account.move.line'].with_context(no_filter=True).search([
        #                 ('account_id', '=', acc_dic[data['GL Code']])
        #                 # ('branch_id', '=', self.env.user.branch_id.id),
        #                 # ('date', '<', '2024-04-01')
        #                 ])
        #             if lines:
        #                 for line in lines:
        #                     line.write({
        #                         'partner_id': partner.id,
        #                         'account_id': 5649
        #                         })
                    # ex_lines = self.env['account.move.line'].search([
                    #     ('account_id', '=', 5649),
                    #     ('branch_id', '=', self.env.user.branch_id.id),
                    #     ('date', '>=', '2024-04-01')
                    #     ])
                    # if ex_lines:
                    #     for line in ex_lines:
                    #         line.write({
                    #             'partner_id': False,
                    #             'account_id': acc_dic[data['GL Code']]
                    #             })
            # if not partner:
            #     partner = partner_obj.search([('name', '=', data['Name'])], limit=1)
            #     partner.property_account_payable_id = int(data['Account ID'])
                        
    def upload_ob_payable(self):
        file_data = self.read_csv_file()
        # moves = self.env['account.move.line'].with_context(no_filter=True).search([('name', '=', False)])
        # for move in moves:
        #     move.branch_id = self.inv_branch_id.id
        #     move.name = move.move_id.name
        # return True
        self.env.cr.execute("""select name from account_move""")
        ref_list = [ref['name'] for ref in self.env.cr.dictfetchall()]
        for data in file_data:
            if data['Bill Number'] in ref_list:
                raise UserError('%s is duplicated'%data['Bill Number'])
            else:
                ref_list.append(data['Bill Number'])
        move_obj = self.env['account.move']
        count = 0
        partner_dic = {}
        partner_obj = self.env['res.partner']
        file_data = self.read_csv_file()
        accounts = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable')
            ])
        acc_dic = {}
        for account in accounts:
            acc_dic.update({account.code: account.id})
        for data in file_data:
            partner = False
            payable_id = acc_dic.get(data['Account Payable/Code'], False)
            if data['Partner Code']:
                partner = partner_obj.search([('partner_code', '=', data['Partner Code'])], limit=1)
                partner.property_account_payable_id = payable_id
            if not partner:
                partner = partner_obj.search([('name', '=', data['Name'])], limit=1)
                if partner:
                    partner.property_account_payable_id = payable_id
            if not payable_id:
                raise UserError('%s is Missing'%data['Account Payable/Code'])
                partner = partner_obj.create({
                        'name': data['Name'],
                        'partner_code': data['Partner Code'],
                        'supplier_rank': 1,
                        'partner_type': 'vendor',
                        'property_account_payable_id': payable_id
                        })
            if not partner:
                raise UserError('%s partner not found'%data['Name'])
            lines = []
            journal_id = self.ob_journal_id.id
            date = datetime.strptime(data['Date'], "%d/%m/%Y")
            if data['CREDIT'] and float(data['CREDIT']) > 0:
                amount = float(data['CREDIT'])
                credit_line = {
                    'partner_id': partner.id,
                    'account_id': payable_id,
                    'credit': amount,
                    'debit': 0,
                    'journal_id': journal_id,
                    'name': data['Bill Number']
                    }
                debit_line = {
                    'account_id': self.suspense_account_id.id,
                    'debit': amount,
                    'credit': 0,
                    'journal_id': journal_id,
                    'name': data['Bill Number']
                    }
                lines.append((0, 0, debit_line))
                lines.append((0, 0, credit_line))
            if data['DEBIT'] and float(data['DEBIT']) > 0:
                amount = float(data['DEBIT'])
                credit_line = {
                    'account_id': self.suspense_account_id.id,
                    'credit': amount,
                    'debit': 0,
                    'journal_id': journal_id,
                    'name': data['Bill Number']
                    }
                debit_line = {
                    'account_id': payable_id,
                    'credit': 0,
                    'debit': amount,
                    'journal_id': journal_id,
                    'partner_id': partner.id,
                    'name': data['Bill Number']
                    }
                lines.append((0, 0, debit_line))
                lines.append((0, 0, credit_line))
            move_vals = {
                'journal_id': journal_id,
                'name': data['Bill Number'],
                'move_name': data['Bill Number'],
                'branch_id': self.inv_branch_id.id,
                'line_ids': lines,
                'date': date,
                'posted_before': True,
                'ref': 'OB-AP',
                'partner_id': partner.id,
                }
            move = move_obj.create(move_vals)
            move.action_post()
        self.inv_branch_id = False
        return True
    
    def update_stock_nolot(self):
        quants = self.env['stock.quant'].search([])
        for quant in quants:
            if quant.lot_id:
                quant.in_date = quant.lot_id.create_date
        return True
        
        file_data = self.read_csv_file()
        codes = []
        missing_products = []
        products_dic = {}
        product_obj = self.env['product.product']
        products = product_obj.search([])
        for product in products:
            if product.default_code:
                products_dic.update({product.default_code: product})
        for data in file_data:
            if data['Available Quantity'] and data['Internal Reference'] not in products_dic:
                missing_products.append(data['Internal Reference'])
        if missing_products:
            raise UserError(list(set(missing_products)))
        lot_dic = {}
        lot_obj = self.env['stock.lot']
        move_vals_dic = {}
        products_qty_dic = {}
        products_date_dic = {}
        file_data = self.read_csv_file()
        
        for data in file_data:
            date = '2024-03-31'
            code = data['Internal Reference']
            if data['Available Quantity']:# and data['UPDATE'] == 'YES' and code not in imported_products_list:
                qty = round(float(data['Available Quantity']), 2)
                product.write({'detailed_type': 'product'})
                if code in products_dic:
                    product = products_dic[code]
                    if data['Cost']:
                        product.write({'standard_price': float(data['Cost'].replace(',', ''))})
                move_vals = {
                    'name': 'OB-SFG',
                    'product_id': product.id,
                    'product_uom': product.uom_id.id,
                    'product_uom_qty': qty,
                    'company_id': self.id,
                    'state': 'confirmed',
                    'location_id': self.inv_location_id.id,
                    'location_dest_id': self.inv_location_dest_id.id,
                    'is_inventory': True,
                    'branch_id': self.inv_branch_id.id,
                    'date': date,
                    'move_line_ids': [(0, 0, {
                        'product_id': product.id,
                        'product_uom_id': product.uom_id.id,
                        'qty_done': qty,
                        'location_id': self.inv_location_id.id,
                        'location_dest_id': self.inv_location_dest_id.id,
                        'company_id': self.id,
                        'branch_id': self.inv_branch_id.id,
                        'date': date,
                        })]
                    }
                ob_count = self.env['account.move'].with_context(no_filter=True).search_count([
                    ('ob', '=', True),
                    ('state', '=', 'posted'),
                    ('branch_id', '=', self.inv_branch_id.id)
                    ])
                movename = 'OB/%s/'%(self.inv_branch_id.code)+str(ob_count+1).zfill(5)
                moves = self.env['stock.move'].with_context(inventory_mode=False, ob=True, move_name=movename, force_period_date=date).create(move_vals)
                moves._action_done()
                moves.write({'date': date})
                moves.move_line_ids.write({'date': date})
                moves.account_move_ids.write({'date': date})
                self.env.cr.execute("""
                    update stock_valuation_layer 
                    set create_date='%s' where id=%s
                    """%(date, moves.stock_valuation_layer_ids.id))
        return True
    
    def update_stock(self):
        file_data = self.read_csv_file()
        codes = []
        missing_products = []
        products_dic = {}
        product_obj = self.env['product.product']
        products = product_obj.search([])
        for product in products:
            if product.default_code:
                products_dic.update({product.default_code: product})
        for data in file_data:
            if data['Available Quantity'] and data['Internal Reference'] not in products_dic:
                missing_products.append(data['Internal Reference'])
        if missing_products:
            raise UserError('Missing Products:\n'+str(list(set(missing_products))))
        lot_dic = {}
        lot_obj = self.env['stock.lot']
        move_vals_dic = {}
        products_qty_dic = {}
        products_date_dic = {}
        file_data = self.read_csv_file()
        
        for data in file_data:
            # date = '2024-05-01'
            # date = datetime.strptime(data['Date'], "%d/%m/%Y").strftime('%Y-%m-%d')
            date = self.inv_date.strftime('%Y-%m-%d')
            code = data['Internal Reference']
            if data['Available Quantity'] and round(float(data['Available Quantity']), 2) > 0:# and data['UPDATE'] == 'YES' and code not in imported_products_list:
                lot = data['Lot Number']
                # date = datetime.strptime(data['Date'], "%d/%m/%Y").strftime('%Y-%m-%d')
                if code in products_dic and lot:
                    product = products_dic[code]
                    product.write({'detailed_type': 'product'})
                    # if data['Cost']:
                    #     product.write({'standard_price': float(data['Cost'].replace(',', ''))})
                    qty = round(float(data['Available Quantity']), 2)
                    lots = lot_obj.search([
                        ('name', '=', lot), 
                        ('product_id', '=', product.id)
                        ])
                    if lots:
                        lot_id = lots[0].id
                    else:
                        lot_id = lot_obj.create({
                            'name': lot,
                            'product_id': product.id,
                            'company_id': self.id
                            }).id
                        self.env.cr.execute("""
                            update stock_lot 
                            set create_date='%s' where id=%s
                        """%(date, lot_id))
                    product_lot = str(product.id)+'_'+str(lot_id)
                    if product_lot in products_qty_dic:
                        products_qty_dic.update({product_lot: products_qty_dic[product_lot]+qty})
                    else:
                        products_qty_dic.update({product_lot: qty})
                    # products_date_dic.update({product_lot: date})
        for product_lot in products_qty_dic:
            product_id = int(product_lot.split('_')[0])
            product = product_obj.browse(product_id)
            lot_id = int(product_lot.split('_')[1])
            move_vals = {
                'name': 'Stock Update-%s'%(self.inv_branch_id.code),
                'product_id': product.id,
                'product_uom': product.uom_id.id,
                'product_uom_qty': products_qty_dic[product_lot],
                'company_id': self.id,
                'state': 'confirmed',
                'location_id': self.inv_location_id.id,
                'location_dest_id': self.inv_location_dest_id.id,
                'is_inventory': True,
                'branch_id': self.inv_branch_id.id,
                'date': date,#products_date_dic[product_lot],#self.inv_date,
                'move_line_ids': [(0, 0, {
                    'product_id': product.id,
                    'product_uom_id': product.uom_id.id,
                    'qty_done': products_qty_dic[product_lot],
                    'location_id': self.inv_location_id.id,
                    'location_dest_id': self.inv_location_dest_id.id,
                    'company_id': self.id,
                    'lot_id': lot_id,
                    'branch_id': self.inv_branch_id.id,
                    'date': date#products_date_dic[product_lot],
                    })]
                }
            # ob_count = self.env['account.move'].with_context(no_filter=True).search_count([
            #     ('ob', '=', True),
            #     ('state', '=', 'posted'),
            #     ('branch_id', '=', self.inv_branch_id.id)
            #     ])
            # movename = 'OBFG/%s/'%(self.inv_branch_id.code)+str(ob_count+1).zfill(6)
            moves = self.env['stock.move'].with_context(inventory_mode=False, force_period_date=date).create(move_vals)
            moves.with_context(branch=self.inv_branch_id.id)._action_done()
            moves.write({'date': date})
            moves.move_line_ids.write({'date': date})
            # moves.stock_valuation_layer_ids.write({'create_date': self.inv_date})
            moves.account_move_ids.write({'date': date})
            self.env.cr.execute("""
                update stock_valuation_layer 
                set create_date='%s' where id=%s
                """%(date, moves.stock_valuation_layer_ids.id))
        # self.inv_branch_id = False
        # self.inv_location_dest_id = False
        return True
    
    def correct_serial_location(self):
        ss_obj = self.env['stock.serial']
        sns = ss_obj.with_context(no_filter=True).search([])
        for sn in sns:
            sn.write({'recompute': not sn.recompute})
        return True
    
    def update_sns(self):
        file_data = self.read_csv_file()
        product_obj = self.env['product.product']
        codes = []
        products_dic = {}
        lot_dic = {}
        lots = []
        for data in file_data:
            if data['Available Quantity']:
                codes.append(data['Internal Reference'])
                lots.append(data['Lot Number'])
        lots = list(set(lots))
        codes = list(set(codes))
        products = product_obj.search([('default_code', 'in', codes)])
        for product in products:
            products_dic.update({product.default_code: product})
        file_data = self.read_csv_file()
        ss_obj = self.env['stock.serial']
        ssl_obj = self.env['stock.serial.line']
        for data in file_data:
            # date = '2024-05-01'
            date = datetime.strptime(data['Manufacturing Date'], "%d-%m-%Y").strftime('%Y-%m-%d')
            sl_no = data['Upload Serial Number'].replace('\n', '')
            if sl_no:# and data['UPDATE'] == 'YES':
                if data['Available Quantity'] and data['Internal Reference'] in products_dic:
                    lot = data['Lot Number']
                    product = products_dic[data['Internal Reference']]
                    prod_lots = self.env['stock.lot'].search([('name', '=', lot), ('product_id', '=', product.id)])
                    if prod_lots:
                        lot_id = prod_lots[0].id
                        sl_vals = {
                            'name': sl_no,
                            'lot_id': lot_id,
                            'date': date,
                            }
                        sl_ids = ss_obj.with_context(no_filter=True).search([('name', '=', sl_no), ('lot_id', '=', lot_id)])
                        if self.loose_ok:
                            sl_vals.update({'initial_qty_manual': product.weight_bag})
                        if sl_ids:
                            sl_id = sl_ids[0].id
                            if round(float(data['Available Quantity']), 2) == round(sl_ids[0].quantity, 2):
                                pass
                            else:
                                ssl_vals = {
                                    'serial_id': sl_id,
                                    'location_id': self.inv_location_id.id,
                                    'location_dest_id': self.inv_location_dest_id.id,
                                    'quantity': data['Available Quantity'],
                                    'date': date
                                    }
                                ssl_obj.create(ssl_vals)
                                sl_ids[0].write({'recompute': not sl_ids[0].recompute})
                        else:
                            sl_id = ss_obj.create(sl_vals)
                            ssl_vals = {
                                'serial_id': sl_id.id,
                                'location_id': self.inv_location_id.id,
                                'location_dest_id': self.inv_location_dest_id.id,
                                'quantity': data['Available Quantity'],
                                'date': date
                                }
                            ssl_obj.create(ssl_vals)
                            sl_id.write({'recompute': not sl_id.recompute})
        return True

    def update_sequences(self):
        moves = self.env['account.move'].with_context(no_filter=True).search([
            ('move_type', 'not in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')), 
            ('state', '=', 'posted'), 
            ('name', '!=', '/'),
            ('branch_id', '=', self.inv_branch_id.id)
            ])
        for move in moves:
            if '/' in move.name:
                name_split = move.name.split('/')[-1]
                move.name = move.name[:-len(name_split)]+name_split.zfill(6)
        return True

    def update_vendors(self):
        file_data = self.read_csv_file()
        partner_obj = self.env['res.partner']
        vendors = partner_obj.search([('supplier_rank', '>', 0)])
        for vendor in vendors:
            seq = ''
            if vendor.partner_type == 'vendor':
                seq = self.env['ir.sequence'].next_by_code('vendor.domestic')
            elif vendor.partner_type == 'vendor_for':
                seq = self.env['ir.sequence'].next_by_code('vendor.foreign')
            vendor.partner_code = seq
        return True

    def update_customers(self):
        # file_data = self.read_csv_file()
        partner_obj = self.env['res.partner']
        customers = partner_obj.search([('customer_rank', '>', 0)])
        for customer in customers:
            if customer.partner_type == 'customer':
                customer.partner_code = self.env['ir.sequence'].next_by_code('customer.domestic')
            elif customer.partner_type == 'customer_exp':
                customer.partner_code = self.env['ir.sequence'].next_by_code('customer.export')
        return True


    def delete_duplicates(self):
        products = self.env['product.template'].search([])
        codes = []
        for product in products:
            if product.default_code in codes:
                product.unlink()
            else:
                codes.append(product.default_code)
        return True
    
    def delete_old_pricelists(self):
        price_obj = self.env['product.pricelist.item']
        old_pls = price_obj.search([])
        old_pls.unlink()
        return True
    
    def upload_pricelists(self):
        file_data = self.read_csv_file()
        codes = []
        for data in file_data:
            codes.append(data['Internal Reference'])
        
        products_dic = {}
        codes = list(set(codes))
        product_obj = self.env['product.template']
        products = product_obj.search([('default_code', 'in', codes)])
        for product in products:
            products_dic.update({product.default_code: product.id})
        file_data = self.read_csv_file()
        price_obj = self.env['product.pricelist.item']
        old_pls = price_obj.search([('pricelist_id', '=', self.new_pricelist_id.id)])
        old_pls.unlink()
        for data in file_data:
            if data['Internal Reference'] in products_dic:
                product_id = products_dic[data['Internal Reference']]
                price_obj.create({
                    'product_tmpl_id': product_id,
                    'fixed_price': data['Basic Rate'],
                    'pricelist_id': self.new_pricelist_id.id
                    })
        return True
    
    def update_group2(self):
        group2_obj = self.env['product.group2']
        product_obj = self.env['product.template']
        group2_dic = {}
        file_data = self.read_csv_file()
        for data in file_data:
            group2_id = False
            if 'Internal Reference' in data and data['Internal Reference']:
                products = product_obj.search([('default_code', '=', data['Internal Reference'])])
                if products:
                    group2_name = data['Product Group 2']
                    if group2_name:
                        if group2_name in group2_dic:
                            group2_id = group2_dic[group2_name]
                        else:
                            groups2 = group2_obj.search([('name', '=', group2_name)])
                            group2_id = groups2 and groups2[0].id or False
                            if not group2_id:
                                group2_id = group2_obj.create({'name': group2_name}).id
                            group2_dic.update({group2_name: group2_id})
                    products[0].write({'product_group2_id': group2_id})
        return True
    
    def update_product_names(self):
        file_data = self.read_csv_file()
        product_obj = self.env['product.template']
        for data in file_data:
            if data['Tally Name']:
                if 'Internal Reference' in data and data['Internal Reference']:
                    products = product_obj.search([('default_code', '=', data['Internal Reference'])])
                    if products:
                        products[0].write({'name': data['Tally Name']})
        return True
    
    def upload_products(self):
        file_data = self.read_csv_file()
        product_obj = self.env['product.template']
        categ_obj = self.env['product.category']
        group1_obj = self.env['product.group1']
        group2_obj = self.env['product.group2']
        group3_obj = self.env['product.group3']
        alt_uom_obj = self.env['product.alt.uom']
        categ_dic, group1_dic, group2_dic, group3_dic = {}, {}, {}, {}
        alt_uom_dic = {}
        alt_uom_id = False
        uom_dic = {'MTR': 5, 'KG': 12, 'LITRE': 10, 'NOS': 1, 'BOX': 32, 'PAIR': 33, 'ROLL': 35, 'SET': 34, 'DRUM': 37}
        tax_dic = {'5%': 84, '12%': 83, '18%': 82}
        type_dic = {'Storable Product': 'product', 'Consumable': 'consu'}
        count = 1
        product_code_dic = {}
        templates = product_obj.search([])
        for template in templates:
            product_code_dic.update({template.default_code: template})
        imported_list = []
        for data in file_data:
            code = data.get('Internal Reference', '')
            if code in imported_list:
                continue
            imported_list.append(code)
            # print(count)
            # vendor_tax = data['Vendor Taxes']
            count += 1
            categ_name = data['Product Category']
            if categ_name in categ_dic:
                categ_id = categ_dic[categ_name]
            else:
                categs = categ_obj.search([('name', '=', categ_name)])
                categ_id = categs and categs[0].id or False
                if not categ_id:
                    categ_id = categ_obj.create({'name': categ_name}).id
                categ_dic.update({categ_name: categ_id})
            group1_id, group2_id, group3_id = False, False, False
            group1_name = data['Product Group 1']
            if group1_name:
                if group1_name in group1_dic:
                    group1_id = group1_dic[group1_name]
                else:
                    groups1 = group1_obj.search([('name', '=', group1_name)])
                    group1_id = groups1 and groups1[0].id or False
                    if not group1_id:
                        group1_id = group1_obj.create({'name': group1_name}).id
                    group1_dic.update({group1_name: group1_id})
            group2_name = data['Product Group 2']
            if group2_name:
                if group2_name in group2_dic:
                    group2_id = group2_dic[group2_name]
                else:
                    groups2 = group2_obj.search([('name', '=', group2_name)])
                    group2_id = groups2 and groups2[0].id or False
                    if not group2_id:
                        group2_id = group2_obj.create({'name': group2_name}).id
                    group2_dic.update({group2_name: group2_id})
            group3_name = data['Product Group 3']
            if group3_name:
                if group3_name in group3_dic:
                    group3_id = group3_dic[group3_name]
                else:
                    groups3 = group3_obj.search([('name', '=', group3_name)])
                    group3_id = groups3 and groups3[0].id or False
                    if not group3_id:
                        group3_id = group3_obj.create({'name': group3_name}).id
                    group3_dic.update({group3_name: group3_id})
            # alt_uom = data['Alt UOM'].upper()
            # if alt_uom:
            #     if alt_uom in alt_uom_dic:
            #         alt_uom_id = alt_uom_dic[alt_uom]
            #     else:
            #         alt_uoms = alt_uom_obj.search([('name', '=', alt_uom)])
            #         alt_uom_id = alt_uoms and alt_uoms[0].id or False
            #         if alt_uom_id:
            #             alt_uom_dic.update({alt_uom: alt_uom_id})
            vals = {
                'name': data.get('Name'),
                'default_code': code,
                'sale_ok': data.get('Can be Sold', False),
                'purchase_ok': data.get('Can be Purchased', False),
                'detailed_type': type_dic[data.get('Product Type', 'Storable Product')],
                'categ_id': categ_id,
                'product_group1_id': group1_id,
                'product_group2_id': group2_id,
                'product_group3_id': group3_id,
                'l10n_in_hsn_code': data.get('HSN/SAC Code', ''),
                # 'alt_uom_id': alt_uom_id,
                'uom_id': uom_dic['KG'],#uom_dic[data['UOM'].upper()],
                'uom_po_id': uom_dic['KG'],#uom_dic[data['UOM'].upper()],
                'standard_price': data.get('Cost', 0),
                'weight_belt': data.get('AUOMUNIT', 0),
                'belt_no': data.get('NOP', 0),
                'product_length': data.get('Length', 0),
                'product_width': data.get('Base Width', 0),
                'product_thickness': data.get('Tread Depth', 0),
                'pattern_name': data.get('Pattern Name', ''),
                'tyre_size': data.get('Tyre Size', ''),
                'supplier_taxes_id': [(4, 82)],
                'taxes_id': [(4, 75)],
                'tracking': 'lot'
                }
            if code in product_code_dic:
                product_code_dic[code].write(vals)
            else:
                product_obj.create(vals)
        return True
    
    def clear_datas(self):
        product_ids = self.env['product.product'].search([('categ_id', '=', self.product_categ_id.id)]).ids
        stock_move_ids = self.env['stock.move'].search([('product_id', 'in', product_ids)]).ids
        acc_move_ids = self.env['account.move'].search([('stock_move_id', 'in', stock_move_ids)]).ids
        
        if product_ids:
            self.env.cr.execute("""delete from stock_quant where product_id in %s"""%(product_ids))
            self.env.cr.execute("""delete from stock_move_line where product_id in %s"""%(product_ids))
            self.env.cr.execute("""delete from stock_move where product_id in %s"""%(product_ids))
            self.env.cr.execute("""delete from stock_valuation_layer where product_id in %s"""%(product_ids))
            self.env.cr.execute("""delete from account_move_line where move_id in %s"""%(acc_move_ids))
            self.env.cr.execute("""delete from account_move where id in %s"""%(acc_move_ids))
        
        #self.env.cr.execute("""delete from mrp_routing_workcenter""")
        #self.env.cr.execute("""delete from mrp_bom_line""")
        #self.env.cr.execute("""delete from mrp_bom""")
        # self.env.cr.execute("""delete from account_partial_reconcile""")
        # self.env.cr.execute("""delete from account_move_line""")
        # self.env.cr.execute("""delete from account_move""")
        # self.env.cr.execute("""delete from stock_quant""")
        # self.env.cr.execute("""delete from stock_move_line""")
        # self.env.cr.execute("""delete from stock_move""")
        # self.env.cr.execute("""delete from stock_valuation_layer""")
        # self.env.cr.execute("""delete from mrp_workorder""")
        # self.env.cr.execute("""delete from mrp_production""")
        # self.env.cr.execute("""delete from stock_lot""")
        # self.env.cr.execute("""delete from stock_picking""")
        # self.env.cr.execute("""delete from stock_serial""")
        # self.env.cr.execute("""delete from stock_serial_line""")
        # self.env.cr.execute("""delete from mrp_serial""")
        # self.env.cr.execute("""delete from mrp_shift_line""")
        # self.env.cr.execute("""delete from picking_serial_line""")
        # self.env.cr.execute("""delete from purchase_order""")
        # self.env.cr.execute("""delete from purchase_order_line""")
        # self.env.cr.execute("""delete from sale_order""")
        # self.env.cr.execute("""delete from sale_order_line""")
        # self.env.cr.execute("""delete from sale_order_template""")
        # self.env.cr.execute("""delete from mrp_unbuild""")
        # self.env.cr.execute("""delete from stock_scrap""")
        # self.env.cr.execute("""delete from stock_landed_cost_lines""")
        # self.env.cr.execute("""delete from stock_landed_cost""")
        # self.env.cr.execute("""delete from mrp_workcenter_productivity""")
        # self.env.cr.execute("""delete from mrp_workcenter""")
        # self.env.cr.execute("""delete from quality_point""")
        # self.env.cr.execute("""delete from quality_check""")
        # self.env.cr.execute("""delete from quality_alert""")
        # self.env.cr.execute("""delete from approval_product_line""")
        # self.env.cr.execute("""delete from approval_request""")
        # user_partners = []
        # users = self.env['res.users'].search(['|',('active', '=', True), ('active', '=', False)])
        # for user in users:
        #     user_partners.append(user.partner_id.id)
        # companies = self.env['res.company'].search([])
        # for compan in companies:
        #     user_partners.append(compan.partner_id.id)
        # branches = self.env['res.branch'].search([])
        # for branch in branches:
        #     user_partners.append(branch.partner_id.id)
        # partners = self.env['res.partner'].search([])
        # for partner in partners:
        #     if partner.id not in user_partners:
        #         partner.unlink()
        return True

class Branch(models.Model):
    _inherit = 'res.branch'
    
    def _login_user(self):
        for quant in self:
            quant.login_user_id = self.env.user.user_access and self.env.user.id or False
            
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    update_text = fields.Text('Update Details')
    correction_date = fields.Datetime('Correction Date')
    category_type = fields.Selection([
        ('rm', 'RM'), 
        ('sfg', 'SFG'), 
        ('fg', 'FG'),
        ('scrap', 'Scrap'),
        ('service', 'Service'),
        ('none', 'None')
        ], 'Category Type')
    product_id = fields.Many2one('product.product')
    categ_id = fields.Many2one('product.category')
    
    def action_clear_serials(self):
        ssls = self.env['stock.serial.location'].search([
            ('branch_id', '=', self.id),
            ])
        # current_date = fields.Datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        # date_india = pytz.utc.localize(datetime.strptime(current_date, '%d-%m-%Y %H:%M:%S')).astimezone(pytz.timezone(('Asia/Calcutta')))
        # current_date = date_india.strftime("%Y-%m-%d %H:%M:%S")
        if not self.correction_date:
            raise UserError('Enter Correction Date.')
        for ssl in ssls:
            ssl.serial_id.action_zero_location_date(ssl.location_id.id, self.correction_date)
        return True
    
    def action_clear_quants(self):
        if not self.category_type:
            raise UserError('Select Category Type')
        domain = [
            ('branch_id', '=', self.id),
            ('product_id.categ_id.category_type', '=', self.category_type)
            ]
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        if self.categ_id:
            domain.append(('product_id.categ_id', '=', self.categ_id.id))
        smls = self.env['stock.move.line'].search(domain)
        product_obj = self.env['product.product']
        product_ids, lot_ids = [], []
        for sml in smls:
            if sml.product_id.detailed_type == 'product':
                product_ids.append(sml.product_id.id)
                if sml.lot_id:
                    lot_ids.append(sml.lot_id.id)
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'), 
            ('branch_id', '=', self.id)
            ])
        product_ids = list(set(product_ids))
        lot_ids = list(set(lot_ids))
        current_date = fields.Datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        inv_location_id = self.env.user.company_id.inv_location_id.id
        if not product_ids:
            return True
        for location in locations:
            prod_lots = self.env['product.product'].get_prodloclot_qty_date(product_ids, location.id, self.correction_date, lot_ids, self.id)
            for product_lot in prod_lots:
                product_id = int(product_lot.split('_')[0])
                product_ids.append(product_id)
                product = product_obj.browse(product_id)
                lot = product_lot.split('_')[1]
                if lot == 'none':
                    lot_id = False
                else:
                    lot_id = int(lot) 
                qty = round(prod_lots[product_lot], 3)
                if qty > 0:
                    move_lines = [(0, 0, {
                        'location_id': location.id, 
                        'location_dest_id': inv_location_id,
                        'lot_id': lot_id,
                        'qty_done': abs(qty),
                        'branch_id': self.id,
                        'state': 'draft',
                        'product_id': product_id,
                        'product_uom_id': product.uom_id.id,
                        'reference': 'Inventory Updation : %s'%current_date,
                        'date': self.correction_date
                        })]
                    new_move = self.env['stock.move'].create({
                        'location_id': location.id, 
                        'location_dest_id': inv_location_id,
                        'branch_id': self.id,
                        'quantity_done': abs(qty),
                        'state': 'confirmed',
                        'product_id': product_id,
                        'product_uom': product.uom_id.id,
                        'product_uom_qty': abs(qty),
                        'name': 'Inventory Updation : %s'%current_date,
                        'move_line_ids': move_lines,
                        'date': self.correction_date
                        })
                    new_move.with_context(force_date=self.correction_date)._action_done()
                elif qty < 0:
                    move_lines = [(0, 0, {
                        'location_id': inv_location_id, 
                        'location_dest_id': location.id,
                        'lot_id': lot_id,
                        'qty_done': abs(qty),
                        'branch_id': self.id,
                        'state': 'draft',
                        'product_id': product_id,
                        'product_uom_id': product.uom_id.id,
                        'reference': 'Inventory Updation : %s'%current_date,
                        'date': self.correction_date
                        })]
                    new_move = self.env['stock.move'].create({
                        'location_id': inv_location_id, 
                        'location_dest_id': location.id,
                        'branch_id': self.id,
                        'quantity_done': abs(qty),
                        'state': 'confirmed',
                        'product_id': product_id,
                        'product_uom': product.uom_id.id,
                        'product_uom_qty': abs(qty),
                        'name': 'Inventory Updation : %s'%current_date,
                        'move_line_ids': move_lines,
                        'date': self.correction_date
                        })
                    new_move.with_context(force_date=self.correction_date)._action_done()
        return True
    
    def action_clear_svls(self):
        if not self.category_type:
            raise UserError('Select Category Type')
        svl_obj = self.env['stock.valuation.layer']
        domain = [
            ('branch_id', '=', self.id),
            ('product_id.categ_id.category_type', '=', self.category_type)
            ]
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        if self.categ_id:
            domain.append(('product_id.categ_id', '=', self.categ_id.id))
        svls = svl_obj.search(domain)
        prod_lots = []
        for svl in svls:
            if not svl.move_line_id:
                svl.update_move_line()
        svls = svl_obj.search(domain)
        no_lot_products = []
        for svl in svls:
            if svl.lot_id:
                prod_lot = '%s_%s'%(str(svl.product_id.id),str(svl.lot_id.id))
                prod_lots.append(prod_lot)
            else:
                no_lot_products.append(svl.product_id.id)
        prod_lots = list(set(prod_lots))
        for prod_lot in prod_lots:
            product_id = int(prod_lot.split('_')[0])
            lot_id = int(prod_lot.split('_')[1])
            prod_lot_svls = svl_obj.search([
                ('product_id', '=', product_id),
                ('lot_id', '=', lot_id),
                ('branch_id', '=', self.id),
                ])
            prod_lot_value = round(sum([prod_lot.value for prod_lot in prod_lot_svls]), 2)
            prod_lot_qty = round(sum([prod_lot.quantity for prod_lot in prod_lot_svls]), 3)
            if prod_lot_value == 0 and prod_lot_qty == 0:
                continue
            prod_lot_insvls = svl_obj.search([
                ('product_id', '=', product_id),
                ('lot_id', '=', lot_id),
                ('branch_id', '=', self.id),
                ('quantity', '>', 0)
                ])
            prod_lot_qty, prod_lot_invalue = 0.0, 0.0
            for prod_lot_in in prod_lot_insvls:
                prod_lot_qty += round(prod_lot_in.quantity, 3)
                value = round(prod_lot_in.quantity * prod_lot_in.unit_cost, 2)
                prod_lot_invalue += value
                prod_lot_in.value = value
                prod_lot_in.correct_svl_jv()
            if prod_lot_qty > 0:
                unit_cost = round(prod_lot_invalue / prod_lot_qty, 3)
            else:
                unit_cost = 0.0
            prod_lot_outsvls = svl_obj.search([
                ('product_id', '=', product_id),
                ('lot_id', '=', lot_id),
                ('branch_id', '=', self.id),
                ('quantity', '<', 0)
                ])
            out_count = len(prod_lot_outsvls.ids)
            if out_count == 1:
                prod_lot_outsvls[0].value = prod_lot_invalue * -1
                prod_lot_outsvls[0].with_context(value=prod_lot_invalue*-1).correct_svl_jv()
            else:
                count = 1
                rem_value = round(prod_lot_invalue, 2)
                for prod_lot_out in prod_lot_outsvls:
                    if count == out_count:
                        prod_lot_out.unit_cost = unit_cost
                        value = -1 * rem_value
                        prod_lot_out.value = value
                        prod_lot_out.with_context(value=value).correct_svl_jv()
                    else:
                        prod_lot_out.unit_cost = unit_cost
                        value = round(unit_cost * prod_lot_out.quantity, 2)
                        prod_lot_out.value = value
                        prod_lot_out.with_context(value=value).correct_svl_jv()
                        rem_value -= abs(value)
                        rem_value = round(rem_value, 2)
                    count += 1
        no_lot_products = list(set(no_lot_products))
        for product_id in no_lot_products:
            prod_svls = svl_obj.search([
                ('product_id', '=', product_id),
                ('lot_id', '=', False),
                ('branch_id', '=', self.id),
                ])
            prod_lot_value = round(sum([prod_lot.value for prod_lot in prod_svls]), 2)
            prod_lot_qty = round(sum([prod_lot.quantity for prod_lot in prod_svls]), 3)
            if prod_lot_value == 0 and prod_lot_qty == 0:
                continue
            prod_lot_insvls = svl_obj.search([
                ('product_id', '=', product_id),
                ('lot_id', '=', False),
                ('branch_id', '=', self.id),
                ('quantity', '>', 0)
                ])
            prod_lot_qty, prod_lot_invalue = 0.0, 0.0
            for prod_lot_in in prod_lot_insvls:
                prod_lot_qty += round(prod_lot_in.quantity, 3)
                value = round(prod_lot_in.quantity * prod_lot_in.unit_cost, 2)
                prod_lot_invalue += value
                prod_lot_in.value = value
                prod_lot_in.correct_svl_jv()
            if prod_lot_qty > 0:
                unit_cost = round(prod_lot_invalue / prod_lot_qty, 3)
            else:
                unit_cost = 0.0
            prod_lot_outsvls = svl_obj.search([
                ('product_id', '=', product_id),
                ('lot_id', '=', False),
                ('branch_id', '=', self.id),
                ('quantity', '<', 0)
                ])
            out_count = len(prod_lot_outsvls.ids)
            if out_count == 1:
                prod_lot_outsvls[0].value = prod_lot_invalue * -1
                prod_lot_outsvls[0].with_context(value=prod_lot_invalue*-1).correct_svl_jv()
            else:
                count = 1
                rem_value = round(prod_lot_invalue, 2)
                for prod_lot_out in prod_lot_outsvls:
                    if count == out_count:
                        prod_lot_out.unit_cost = unit_cost
                        value = -1 * rem_value
                        prod_lot_out.value = value
                        prod_lot_out.with_context(value=value).correct_svl_jv()
                    else:
                        prod_lot_out.unit_cost = unit_cost
                        value = round(unit_cost * prod_lot_out.quantity, 2)
                        prod_lot_out.value = value
                        prod_lot_out.with_context(value=value).correct_svl_jv()
                        rem_value -= abs(value)
                        rem_value = round(rem_value, 2)
                    count += 1
        return True
    
    def action_correct_svlsml(self):
        smls = self.env['stock.move.line'].search([
            ('branch_id', '=', self.id), 
            ('state', '=', 'done'),
            ('it_ok', '!=', True),
            ('qty_done', '!=', 0)
            ])
        svls = self.env['stock.valuation.layer'].search([('branch_id', '=', self.id)])
        svl_dic = {}
        svl_tot_qty = 0.0
        for svl in svls:
            if svl.move_line_id in svl_dic:
                svl.delete_svl_am()
            else:
                svl_dic.update({svl.move_line_id: svl})
                svl_tot_qty += round(svl.quantity, 3)
        missing_smls = []
        sml_tot_qty = 0.0
        for sml in smls:
            if sml.product_id.detailed_type != 'product' or sml.product_id.categ_id.property_valuation == 'manual_periodic':
                continue
            sml_qty = round(sml.qty_done, 3)
            if sml in svl_dic:
                svl = svl_dic[sml]
                if sml.location_dest_id.usage == 'internal':
                    sml_tot_qty += sml_qty
                    svl.quantity = sml_qty
                elif sml.location_id.usage == 'internal':
                    sml_tot_qty -= sml_qty
                    svl.quantity = -1 * sml_qty
            else:
                svl_obj = self.env['stock.valuation.layer']
                if sml.location_dest_id.usage == 'internal':
                    svl_vals = sml.move_id._prepare_common_svl_vals()
                    unit_cost = sml.move_id.price_unit
                    svl_vals.update({
                        'quantity': sml_qty,
                        'unit_cost': unit_cost,
                        'value': round(unit_cost*sml_qty, 3),
                        'lot_id': sml.lot_id and sml.lot_id.id or False,
                        'move_line_id': sml.id
                        })
                    sml.unit_cost = unit_cost
                    new_svl = svl_obj.sudo().create(svl_vals)
                    am_vals = new_svl.stock_move_id.with_context(force_period_date=sml.date)._account_entry_move(round(new_svl.quantity, 3), new_svl.description, new_svl.id, new_svl.value)
                    if am_vals:
                        account_moves = self.env['account.move'].sudo().create(am_vals)
                        account_moves._post()
                        new_svl.account_move_id = account_moves.id
                    self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (sml.date, new_svl.id))
                elif sml.location_id.usage == 'internal':
                    svl_vals = sml.move_id._prepare_common_svl_vals()
                    unit_cost = sml.move_id.price_unit
                    svl_vals.update({
                        'quantity': -1*sml_qty,
                        'unit_cost': unit_cost,
                        'value': round(-1*unit_cost*sml_qty, 3),
                        'lot_id': sml.lot_id and sml.lot_id.id or False,
                        'move_line_id': sml.id
                        })
                    sml.unit_cost = unit_cost
                    new_svl = svl_obj.sudo().create(svl_vals)
                    am_vals = new_svl.stock_move_id.with_context(force_period_date=sml.date)._account_entry_move(round(new_svl.quantity, 3), new_svl.description, new_svl.id, new_svl.value)
                    if am_vals:
                        account_moves = self.env['account.move'].sudo().create(am_vals)
                        account_moves._post()
                        new_svl.account_move_id = account_moves.id
                    self._cr.execute("""update stock_valuation_layer set create_date='%s' where id=%s"""% (sml.date, new_svl.id))
                missing_smls.append(sml.id)
        return True
    
    def action_find_diff(self):
        product_obj = self.env['product.product']
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'), 
            ('branch_id', '=', self.id)
            ])
        update_text = ''
        for location in locations:
            loc_update_text = ''
            products_qty_details = self.get_sslproducts_qty_dic(location.id)
            products_qty_dic = products_qty_details[3]
            lot_ids = products_qty_details[1]
            product_ids = products_qty_details[2]
            if not product_ids or not lot_ids:
                continue
            sml_qty_dic = product_obj.get_prodcodeloclot_qty(product_ids, location.id, lot_ids, self.id)
            for product_lot in products_qty_dic:
                qty = round(products_qty_dic[product_lot], 3)
                sml_qty = round(sml_qty_dic.get(product_lot, 0.0), 3)
                if qty != sml_qty:
                    text = 'sl_qty: %s, sml_qty: %s'%(str(qty), str(sml_qty))
                    loc_update_text += product_lot + text + '\n'
            for product_lot in sml_qty_dic:
                qty = round(products_qty_dic[product_lot], 3)
                sml_qty = round(sml_qty_dic.get(product_lot, 0.0), 3)
                if qty != sml_qty:
                    text = 'sl_qty: %s, sml_qty: %s'%(str(qty), str(sml_qty))
                    loc_update_text += product_lot + text + '\n'
            if loc_update_text:
                update_text += location.name + ':\n' + loc_update_text + '\n'
        self.update_text = update_text
        return True
    
    def action_sml_svl_diff(self):
        product_obj = self.env['product.product']
        categs = self.env['product.category'].search([])
        categ_update_text = ''
        for categ in categs:
            product_ids = product_obj.search([
                ('detailed_type', '!=', 'service'),
                ('categ_id', '=', categ.id)
                ]).ids
            update_text = ''
            if product_ids:
                sml_lot_qty_dic = product_obj.get_sml_lot_qty(self.id, product_ids=product_ids)
                svl_lot_qty_dic = product_obj.get_svl_lot_qty(self.id, product_ids=product_ids)
                
                missing_list = []
                for prodlot in sml_lot_qty_dic:
                    sml_qty = sml_lot_qty_dic.get(prodlot, 0.0)
                    svl_qty = svl_lot_qty_dic.get(prodlot, 0.0)
                    if sml_qty != svl_qty:
                        if prodlot not in missing_list:
                            missing_list.append(prodlot)
                            update_text += '%s-sml_qty: %s, svl_qty : %s\n'%(prodlot, sml_qty, svl_qty)
                for prodlot in svl_lot_qty_dic:
                    sml_qty = sml_lot_qty_dic.get(prodlot, 0.0)
                    svl_qty = svl_lot_qty_dic.get(prodlot, 0.0)
                    if sml_qty != svl_qty:
                        if prodlot not in missing_list:
                            missing_list.append(prodlot)
                            update_text += '%s-sml_qty: %s, svl_qty : %s\n'%(prodlot, sml_qty, svl_qty)
            if update_text:
                categ_update_text += categ.name + '\n' + update_text + '\n'
        self.update_text = categ_update_text
        return True
    
    def get_sslproducts_qty_dic(self, location_id):
        ssl_obj = self.env['stock.serial.location']
        ss_obj = self.env['stock.serial']
        product_ids = []
        ssls = ssl_obj.search([('branch_id', '=', self.id)])
        for ssl in ssls:
            product_ids.append(ssl.product_id.id)
        product_ids = list(set(product_ids))
        lot_ids = []
        products_qty_dic = {}
        productcode_qty_dic = {}
        in_dic = ssl_obj.get_ssl_qtys(product_ids, location_id)
        serial_ids = [serial_id for serial_id in in_dic]
        serial_ids = list(set(serial_ids))
        for serial_id in serial_ids:
            serial = ss_obj.with_context(no_filter=True).browse(serial_id)
            product = serial.product_id
            qty = in_dic[serial_id]
            product_lot = '%s_%s'%(str(product.id),str(serial.lot_id.id))
            product_lot_code = '%s_%s'%(str(product.default_code),str(serial.lot_id.name))
            lot_ids.append(serial.lot_id.id)
            if product_lot in products_qty_dic:
                products_qty_dic.update({product_lot: products_qty_dic[product_lot]+qty})
            else:
                products_qty_dic.update({product_lot: qty})
            if product_lot_code in productcode_qty_dic:
                productcode_qty_dic.update({product_lot_code: productcode_qty_dic[product_lot_code]+qty})
            else:
                productcode_qty_dic.update({product_lot_code: qty})
        return [products_qty_dic, list(set(lot_ids)), product_ids, productcode_qty_dic]
    
    def action_correct_slsml(self):
        product_obj = self.env['product.product']
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'), 
            ('branch_id', '=', self.id)
            ])
        lot_ids = []
        current_date = fields.Datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        date_india = pytz.utc.localize(datetime.strptime(current_date, '%d-%m-%Y %H:%M:%S')).astimezone(pytz.timezone(('Asia/Calcutta')))
        current_date = date_india.strftime("%d-%m-%Y %H:%M:%S")
        inv_location_id = self.env.user.company_id.inv_location_id.id
        for location in locations:
            products_qty_details = self.get_sslproducts_qty_dic(location.id)
            products_qty_dic = products_qty_details[0]
            lot_ids = products_qty_details[1]
            product_ids = products_qty_details[2]
            if not product_ids or not lot_ids:
                continue
            sml_qty_dic = product_obj.get_prodloclot_qty(product_ids, location.id, lot_ids, branch_id=self.id)
            for product_lot in products_qty_dic:
                qty = round(products_qty_dic[product_lot], 3)
                sml_qty = round(sml_qty_dic.get(product_lot, 0.0), 3)
                diff = qty - sml_qty
                product_id = int(product_lot.split('_')[0])
                product_ids.append(product_id)
                product = product_obj.browse(product_id)
                lot_id = int(product_lot.split('_')[1])
                if product_lot in sml_qty_dic:
                    if diff < 0:
                        move_lines = [(0, 0, {
                            'location_id': location.id, 
                            'location_dest_id': inv_location_id,
                            'branch_id': self.id,
                            'lot_id': lot_id,
                            'qty_done': abs(diff),
                            'state': 'draft',
                            'product_id': product_id,
                            'product_uom_id': product.uom_id.id,
                            'reference': 'Inventory Updation : %s'%current_date,
                            })]
                        new_move = self.env['stock.move'].create({
                            'location_id': location.id, 
                            'location_dest_id': inv_location_id,
                            'branch_id': self.id,
                            'quantity_done': abs(diff),
                            'state': 'confirmed',
                            'product_id': product_id,
                            'product_uom': product.uom_id.id,
                            'product_uom_qty': abs(diff),
                            'name': 'Inventory Updation : %s'%current_date,
                            'move_line_ids': move_lines,
                            })
                        new_move._action_done()
                    elif diff > 0:
                        move_lines = [(0, 0, {
                            'location_id': inv_location_id, 
                            'location_dest_id': location.id,
                            'branch_id': self.id,
                            'lot_id': lot_id,
                            'qty_done': abs(diff),
                            'state': 'draft',
                            'product_id': product_id,
                            'product_uom_id': product.uom_id.id,
                            'reference': 'Inventory Updation : %s'%current_date,
                            })]
                        new_move = self.env['stock.move'].create({
                            'location_id': inv_location_id, 
                            'location_dest_id': location.id,
                            'branch_id': self.id,
                            'quantity_done': abs(diff),
                            'state': 'confirmed',
                            'product_id': product_id,
                            'product_uom': product.uom_id.id,
                            'product_uom_qty': abs(diff),
                            'name': 'Inventory Updation : %s'%current_date,
                            'move_line_ids': move_lines,
                            })
                        new_move._action_done()
                else:
                    move_lines = [(0, 0, {
                        'location_id': location.id, 
                        'location_dest_id': inv_location_id,
                        'lot_id': lot_id,
                        'branch_id': self.id,
                        'qty_done': qty,
                        'state': 'draft',
                        'product_id': product_id,
                        'product_uom_id': product.uom_id.id,
                        'reference': 'Inventory Updation : %s'%current_date,
                        })]
                    new_move = self.env['stock.move'].create({
                        'location_id': location.id, 
                        'location_dest_id': inv_location_id,
                        'branch_id': self.id,
                        'quantity_done': qty,
                        'state': 'confirmed',
                        'product_id': product_id,
                        'product_uom': product.uom_id.id,
                        'product_uom_qty': qty,
                        'name': 'Inventory Updation : %s'%current_date,
                        'move_line_ids': move_lines,
                        })
                    new_move._action_done()
            sml_qty_dic = product_obj.get_prodloclot_qty(product_ids, location.id, lot_ids, self.id)
            for product_lot in sml_qty_dic:
                qty = round(sml_qty_dic[product_lot], 3)
                product_id = int(product_lot.split('_')[0])
                product_ids.append(product_id)
                product = product_obj.browse(product_id)
                lot_id = int(product_lot.split('_')[1])
                if qty > 0:
                    if product_lot not in products_qty_dic:
                        move_lines = [(0, 0, {
                            'location_id': location.id, 
                            'location_dest_id': inv_location_id,
                            'branch_id': self.id,
                            'lot_id': lot_id,
                            'qty_done': qty,
                            'state': 'draft',
                            'product_id': product_id,
                            'product_uom_id': product.uom_id.id,
                            'reference': 'Inventory Updation : %s'%current_date,
                            })]
                        new_move = self.env['stock.move'].create({
                            'location_id': location.id, 
                            'location_dest_id': inv_location_id,
                            'branch_id': self.id,
                            'quantity_done': qty,
                            'state': 'confirmed',
                            'product_id': product_id,
                            'product_uom': product.uom_id.id,
                            'product_uom_qty': qty,
                            'name': 'Inventory Updation : %s'%current_date,
                            'move_line_ids': move_lines,
                            })
                        new_move._action_done()
                elif qty < 0:
                    if product_lot not in products_qty_dic:
                        move_lines = [(0, 0, {
                            'location_id': inv_location_id, 
                            'location_dest_id': location.id,
                            'branch_id': self.id,
                            'lot_id': lot_id,
                            'qty_done': abs(qty),
                            'state': 'draft',
                            'product_id': product_id,
                            'product_uom_id': product.uom_id.id,
                            'reference': 'Inventory Updation : %s'%current_date,
                            })]
                        new_move = self.env['stock.move'].create({
                            'location_id': inv_location_id, 
                            'location_dest_id': location.id,
                            'branch_id': self.id,
                            'quantity_done': abs(qty),
                            'state': 'confirmed',
                            'product_id': product_id,
                            'product_uom': product.uom_id.id,
                            'product_uom_qty': abs(qty),
                            'name': 'Inventory Updation : %s'%current_date,
                            'move_line_ids': move_lines,
                            })
                        new_move._action_done()
        return True
    
    def action_correct_sml_quant(self):
        smls = self.env['stock.move.line'].search([('branch_id', '=', self.id)])
        product_obj = self.env['product.product']
        quant_obj = self.env['stock.quant']
        product_ids, lot_ids = [], []
        for sml in smls:
            if sml.product_id.detailed_type == 'product':
                product_ids.append(sml.product_id.id)
                if sml.lot_id:
                    lot_ids.append(sml.lot_id.id)
        locations = self.env['stock.location'].search([
            ('usage', '=', 'internal'), 
            ('branch_id', '=', self.id)
            ])
        product_ids = list(set(product_ids))
        lot_ids = list(set(lot_ids))
        current_date = fields.Datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        inv_location_id = self.env.user.company_id.inv_location_id.id
        negative_stocks = []
        total_qty = 0.0
        for location in locations:
            prod_lots = self.env['product.product'].get_prodloclot_qty(product_ids, location.id, lot_ids, branch_id=self.id)
            for product_lot in prod_lots:
                product_id = int(product_lot.split('_')[0])
                product_ids.append(product_id)
                product = product_obj.browse(product_id)
                lot_id = int(product_lot.split('_')[1])
                qty = round(prod_lots[product_lot], 3)
                total_qty += qty
                if qty > 0:
                    product_quants = quant_obj.search([
                        ('branch_id', '=', self.id),
                        ('location_id', '=', location.id),
                        ('lot_id', '=', lot_id),
                        ('product_id', '=', product_id)])
                    if not product_quants:
                        quant_obj.create({
                            'branch_id': self.id,
                            'location_id': location.id,
                            'lot_id': lot_id,
                            'product_id': product_id,
                            })
                elif qty < 0:
                    negative_stocks.append(product_lot)
                    move_lines = [(0, 0, {
                        'location_id': inv_location_id, 
                        'location_dest_id': location.id,
                        'lot_id': lot_id,
                        'qty_done': abs(qty),
                        'branch_id': self.id,
                        'state': 'draft',
                        'product_id': product_id,
                        'product_uom_id': product.uom_id.id,
                        'reference': 'Inventory Updation : %s'%current_date,
                        })]
                    new_move = self.env['stock.move'].create({
                        'location_id': inv_location_id, 
                        'location_dest_id': location.id,
                        'branch_id': self.id,
                        'quantity_done': abs(qty),
                        'state': 'confirmed',
                        'product_id': product_id,
                        'product_uom': product.uom_id.id,
                        'product_uom_qty': abs(qty),
                        'name': 'Inventory Updation : %s'%current_date,
                        'move_line_ids': move_lines,
                        })
                    new_move._action_done()
                elif qty == 0:
                    product_quants = quant_obj.search([
                        ('branch_id', '=', self.id),
                        ('location_id', '=', location.id),
                        ('lot_id', '=', lot_id),
                        ('product_id', '=', product_id)])
                    if product_quants:
                        product_quants.sudo().unlink()
        return True
