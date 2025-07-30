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
from odoo.tools import pycompat
from odoo.tools.float_utils import float_round

class Category(models.Model):
    _inherit = 'product.category'
    
    category_type = fields.Selection([
        ('rm', 'RM'), 
        ('sfg', 'SFG'), 
        ('fg', 'FG'),
        ('scrap', 'Scrap'),
        ('service', 'Service'),
        ('none', 'None')
        ], 'Category Type')
    production_location_id = fields.Many2one('stock.location', 'Production Location')
    fg_type = fields.Selection([
        ('pctr', 'PCTR'),
        ('ct', 'CT'),
        ('bg', 'BG'),
        ('bvc', 'BVC')], string='FG Type')
    conversion_cost = fields.Float('Conversion Cost')

class AltUoM(models.Model):
    _name = 'product.alt.uom'
    _description = 'Product Alt UoM'
    
    name = fields.Char('Name', required=True)
    code = fields.Selection([('1', '1'), ('2', '2'), ('3', '3'), ('4', '4')], required=True)
    type = fields.Selection([('base', 'Base'), ('smaller', 'Smaller'), ('bigger', 'Bigger')], required=True)
    
class ProductGroup1(models.Model):
    _name = 'product.group1'
    _description = 'Product Group1'
    
    name = fields.Char('Name', required=True)

class ProductGroup2(models.Model):
    _name = 'product.group2'
    _description = 'Product Group2'
    
    name = fields.Char('Name', required=True)

class ProductGroup3(models.Model):
    _name = 'product.group3'
    _description = 'Product Group3'
    
    name = fields.Char('Name', required=True)
    skip_quality = fields.Boolean('Skip QC')

class ProductGroup4(models.Model):
    _name = 'product.group4'
    _description = 'Product Group4'
    
    name = fields.Char('Name', required=True)


class HsCode(models.Model):
    _name = 'hs.code'
    _description = 'HS Code'
    
    name = fields.Char('HSN/SAC Code', required=True)
    desc = fields.Char('Description')
    uqc = fields.Char('UQC', required=False)
    type = fields.Char('Type of Supply', required=False)

class Product(models.Model):
    _inherit = 'product.product'
    
    def _compute_quantities_dict(self, lot_id, owner_id, package_id, from_date=False, to_date=False):
        domain_quant_loc, domain_move_in_loc, domain_move_out_loc = self._get_domain_locations()
        domain_quant = [('product_id', 'in', self.ids)] + domain_quant_loc
        dates_in_the_past = False
        # only to_date as to_date will correspond to qty_available
        to_date = fields.Datetime.to_datetime(to_date)
        if to_date and to_date < fields.Datetime.now():
            dates_in_the_past = True

        domain_move_in = [('product_id', 'in', self.ids)] + domain_move_in_loc
        domain_move_out = [('product_id', 'in', self.ids)] + domain_move_out_loc
        if lot_id is not None:
            domain_quant += [('lot_id', '=', lot_id)]
        if owner_id is not None:
            domain_quant += [('owner_id', '=', owner_id)]
            domain_move_in += [('restrict_partner_id', '=', owner_id)]
            domain_move_out += [('restrict_partner_id', '=', owner_id)]
        if package_id is not None:
            domain_quant += [('package_id', '=', package_id)]
        if dates_in_the_past:
            domain_move_in_done = list(domain_move_in)
            domain_move_out_done = list(domain_move_out)
        if from_date:
            date_date_expected_domain_from = [('date', '>=', from_date)]
            domain_move_in += date_date_expected_domain_from
            domain_move_out += date_date_expected_domain_from
        if to_date:
            date_date_expected_domain_to = [('date', '<=', to_date)]
            domain_move_in += date_date_expected_domain_to
            domain_move_out += date_date_expected_domain_to

        Move = self.env['stock.move'].with_context(active_test=False)
        Quant = self.env['stock.quant'].with_context(active_test=False)
        domain_move_in_todo = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_in
        domain_move_out_todo = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_out
        moves_in_res = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_in_todo, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
        moves_out_res = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_out_todo, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
        quants_res = dict((item['product_id'][0], item['quantity']) for item in Quant._read_group(domain_quant, ['product_id', 'quantity'], ['product_id'], orderby='id'))
        reserved_quants = {}
        quants = Quant.search(domain_quant)
        for quant in quants:
            reserved_quants.update({quant.product_id.id: quant.reserved_quantity})
        if dates_in_the_past:
            # Calculate the moves that were done before now to calculate back in time (as most questions will be recent ones)
            domain_move_in_done = [('state', '=', 'done'), ('date', '>', to_date)] + domain_move_in_done
            domain_move_out_done = [('state', '=', 'done'), ('date', '>', to_date)] + domain_move_out_done
            moves_in_res_past = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_in_done, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
            moves_out_res_past = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_out_done, ['product_id', 'product_qty'], ['product_id'], orderby='id'))

        res = dict()
        for product in self.with_context(prefetch_fields=False):
            origin_product_id = product._origin.id
            product_id = product.id
            if not origin_product_id:
                res[product_id] = dict.fromkeys(
                    ['qty_available', 'free_qty', 'incoming_qty', 'outgoing_qty', 'virtual_available'],
                    0.0,
                )
                continue
            rounding = product.uom_id.rounding
            res[product_id] = {}
            if dates_in_the_past:
                qty_available = quants_res.get(origin_product_id, 0.0) - moves_in_res_past.get(origin_product_id, 0.0) + moves_out_res_past.get(origin_product_id, 0.0)
            else:
                qty_available = quants_res.get(origin_product_id, 0.0)
            reserved_quantity = reserved_quants.get(origin_product_id, 0.0)
            res[product_id]['qty_available'] = float_round(qty_available, precision_rounding=rounding)
            res[product_id]['free_qty'] = float_round(qty_available - reserved_quantity, precision_rounding=rounding)
            res[product_id]['incoming_qty'] = float_round(moves_in_res.get(origin_product_id, 0.0), precision_rounding=rounding)
            res[product_id]['outgoing_qty'] = float_round(moves_out_res.get(origin_product_id, 0.0), precision_rounding=rounding)
            res[product_id]['virtual_available'] = float_round(
                qty_available + res[product_id]['incoming_qty'] - res[product_id]['outgoing_qty'],
                precision_rounding=rounding)

        return res
    
    def get_product_length_us(self):
        template = self.product_tmpl_id
        product_length_us = '%s (%s mm)'%(str(template.product_length_us or ''), str(round(template.product_length_mm, 2)))
        return product_length_us
    
    def get_product_width_us(self):
        template = self.product_tmpl_id
        product_width_us = '%s (%s mm)'%(str(template.product_width_us or ''), str(round(template.product_width, 2)))
        return product_width_us
    
class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    @api.depends('weight_belt', 'belt_no')
    def _compute_weight_bag(self):
        for product in self:
            product.weight_bag = product.weight_belt * product.belt_no
    
    @api.depends('categ_id', 'categ_id.category_type')
    def _compute_fg(self):
        for product in self:
            if product.categ_id and product.categ_id.category_type and product.categ_id.category_type == 'fg':
                product.fg = True
            else:
                product.fg = False
    
    def _compute_max_retail_price(self):
        for product in self:
            pricelist_objs = self.env['product.pricelist.item'].search([('product_tmpl_id', '=', product.id)])
            result = 0
            if pricelist_objs:
                price_list = []
                for objs in pricelist_objs:
                    price_list.append(objs.fixed_price)
                result = max(price_list)
            product.MRP_product = result * 1.18
            
    MRP_product = fields.Monetary('MRP', compute='_compute_max_retail_price')
    alt_uom_id = fields.Many2one('product.alt.uom', 'Alternate UoM')
    weight_belt = fields.Float('Per Unit Weight')
    belt_no = fields.Integer('No. of Packages')
    tyre_size = fields.Char('Tyre Size')
    weight_bag = fields.Float('Gross Weight', compute='_compute_weight_bag', store=True)
    tolerance = fields.Float('Tolerance', digits=(16, 3))
    
    product_group1_id = fields.Many2one('product.group1', 'Product Group1')
    product_group2_id = fields.Many2one('product.group2', 'Product Group2')
    product_group3_id = fields.Many2one('product.group3', 'Product Group3')
    product_group4_id = fields.Many2one('product.group4', 'Product Group4')
    conversion_cost = fields.Float('Conversion Cost')
    
    master_batch = fields.Boolean('Master Batch')
    fg = fields.Boolean('FG', compute='_compute_fg', store=True)
    curing_ok = fields.Boolean('Curing SFG')
    sfg_type = fields.Selection([('mb', 'MB'), ('fb', 'FB')])
    
    lot_sequence_id = fields.Many2one('ir.sequence', 'Lot Sequence')
    serial_sequence_id = fields.Many2one('ir.sequence', 'Serial No Sequence')
    
    product_length = fields.Float('Length(Inch)')
    product_length_us = fields.Char('Length-US')
    product_length_mm = fields.Float('Length(mm)')
    product_width = fields.Float('Width')
    product_width_us = fields.Char('Width-US')
    product_thickness = fields.Float('Thickness')
    pattern_name = fields.Char('Pattern Name')
    product_compound_id = fields.Many2one('product.template', 'Compound Product')
    conversion_cost = fields.Float('Conversion Cost')
    qc_ok = fields.Boolean('QC Required?')
    hs_code = fields.Char("ZZZ1")
    l10n_in_hsn_code = fields.Char("ZZZ2")
    l10n_in_hsn_description = fields.Char("ZZZ3")
    hs_code_id = fields.Many2one('hs.code', 'HSN Code')
    invoice_policy = fields.Selection(
        [('order', 'Ordered quantities'),
         ('delivery', 'Delivered quantities')], string='Invoicing Policy',
        compute='_compute_invoice_policy', store=True, readonly=False, precompute=True,
        help='')
    
    @api.depends('type')
    def _compute_invoice_policy(self):
        self.filtered(lambda t: t.type == 'consu' or not t.invoice_policy).invoice_policy = 'order'
        
    def update_hsn(self):
        hsn_dic = {}
        for hsn in self.env['hs.code'].search([]):
            hsn_dic.update({hsn.name: hsn.id})
        for product in self.search([]):
            if product.l10n_in_hsn_code:
                hsn = product.l10n_in_hsn_code.replace(' ', '')
                if hsn in hsn_dic:
                    product.hs_code_id = hsn_dic[hsn]
                else:
                    hs_code_id = self.env['hs.code'].create({'name': hsn}).id
                    hsn_dic.update({hsn: hs_code_id})
                    product.hs_code_id = hs_code_id
        return True
    
class Pricelist(models.Model):
    _inherit = 'product.pricelist'
    
    data_file = fields.Binary('Data File')
    data_file_name = fields.Char('Data File Name')
    additional_price = fields.Float('Additional Price')
    
    price_update = fields.Selection([
        ('categ', 'Category'), ('gp1', 'Product Group1'),
        ('gp2', 'Product Group2'), ('gp3', 'Product Group3')
        ], 'Pricelist Update For')
    product_categ_id = fields.Many2one('product.category', 'Product Category')
    product_group1_id = fields.Many2one('product.group1', 'Product Group1')
    product_group2_id = fields.Many2one('product.group2', 'Product Group2')
    product_group3_id = fields.Many2one('product.group3', 'Product Group3')
    
    def update_prices(self):
        if self.price_update == 'categ':
            domain = [('product_tmpl_id.categ_id', '=', self.product_categ_id.id)]
        elif self.price_update == 'gp1':
            domain = [('product_tmpl_id.product_group1_id', '=', self.product_group1_id.id)]
        elif self.price_update == 'gp2':
            domain = [('product_tmpl_id.product_group2_id', '=', self.product_group2_id.id)]
        elif self.price_update == 'gp3':
            domain = [('product_tmpl_id.product_group3_id', '=', self.product_group3_id.id)]
        domain.append(('pricelist_id', '=', self.id))
        pricellists = self.env['product.pricelist.item'].search(domain)
        for pricellist in pricellists:
            pricellist.fixed_price = pricellist.fixed_price + self.additional_price
        self.additional_price = 0
        return True
    
    def read_csv_file(self):
        import_file = BytesIO(base64.decodebytes(self.data_file))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=',')
        return reader
    
    def delete_old_pricelists(self):
        price_obj = self.env['product.pricelist.item']
        old_pls = price_obj.search([('pricelist_id', '=', self.id)], limit=800)
        old_pls.unlink()
        return True
    
    def upload_pricelists(self):
        # file_data = self.read_csv_file()
        data_list = []
        file_data = pycompat.csv_reader(BytesIO(base64.decodebytes(self.data_file)), quotechar='"', delimiter=',')
        codes = []
        count = 1
        for data in file_data:
            count += 1
            data_list.append(data)
        header = data_list[0]
        for data in data_list[1:]:
            code = data[header.index('Internal Reference')]
            codes.append(code)
        products_dic = {}
        codes = list(set(codes))
        product_obj = self.env['product.template']
        products = product_obj.search([('default_code', 'in', codes)])
        for product in products:
            products_dic.update({product.default_code: product.id})
        # file_data = self.read_csv_file()
        price_obj = self.env['product.pricelist.item']
        for data in data_list[1:]:
            code = data[header.index('Internal Reference')]
            if code in products_dic:
                product_id = products_dic[code]
                price_obj.create({
                    'product_tmpl_id': product_id,
                    'fixed_price': data[header.index('Basic Rate')],
                    'pricelist_id': self.id
                    })
        return True
    
    