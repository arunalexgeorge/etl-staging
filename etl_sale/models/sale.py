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

from collections import defaultdict
from odoo import _, api, fields, models, Command, tools
from odoo.exceptions import UserError, ValidationError
from cgitb import reset
from odoo.tools import float_is_zero, float_compare, float_round
import logging
logger = logging.getLogger(__name__)

class Transporter(models.Model):
    _name = 'eway.transporter'
    _description = 'Transporter'
    
    name = fields.Char('Transporter Name', required=True)
    gst = fields.Char('GST', required=True)
    branch_id = fields.Many2one('res.branch', 'Branch', required=True)
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        args = args or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            args += [('branch_id', 'in', branches_ids)]
        return super(Transporter, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
    @api.model
    def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        domain = domain or []
        if 'no_filter' in self._context:
            pass
        else:
            if 'allowed_branch_ids' in self._context:
                branches_ids = self._context['allowed_branch_ids']
            else:
                branches_ids = self.env.user.branch_ids.ids
            domain += [('branch_id', 'in', branches_ids)]
        return super(Transporter, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
class SalesOrder(models.Model):
    _inherit = 'sale.order'
    
    @api.depends('user_id', 'company_id', 'partner_id')
    def _compute_warehouse_id(self):
        for order in self:
            branch_id, warehouse_id = False, False
            if self.env.user.branch_id:
                branch_id = self.env.user.branch_id.id
            if branch_id:
                branched_warehouse = self.env['stock.warehouse'].search([('branch_id','=',branch_id)])
                if branched_warehouse:
                    warehouse_id = branched_warehouse.ids[0]
        
            order.warehouse_id = warehouse_id
    
    @api.depends('partner_id', 'partner_id.region_id')
    def _compute_region(self):
        for order in self:
            if order.partner_id and order.partner_id.region_id:
                order.region_id = order.partner_id.region_id.id
            else:
                order.region_id = False
    
    @api.depends('order_line', 'order_line.product_uom_qty')
    def _compute_total_weight(self):
        for order in self:
            order.total_weight = sum([line.product_uom_qty for line in order.order_line])
    
    @api.depends('partner_id', 'branch_id', 'partner_id.state_id', 'branch_id.partner_id', 'branch_id.partner_id.state_id')
    def _compute_fiscal_position(self):
        for order in self:
            company = self.env['res.company'].browse(1)
            if order.partner_id and order.partner_id.state_id and order.branch_id:
                if order.partner_id.state_id.id == order.branch_id.partner_id.state_id.id:
                    order.fiscal_position_id = company.gst_fiscal_position_id.id
                else:
                    order.fiscal_position_id = company.igst_fiscal_position_id.id
            else:
                order.fiscal_position_id = False
    
    @api.depends('state', 'date_order')
    def _compute_fiscal_year(self):
        for order in self:
            fiscal_year = ''
            if order.date_order:
                fy = order.company_id.compute_fiscalyear_dates(order.date_order)
                fiscal_year = fy['date_from'].strftime('%y') + fy['date_to'].strftime('%y')
            order.fiscal_year = fiscal_year
    
    sales_executive_id = fields.Many2one('hr.employee', 'Sales Executive')
    zonal_head_id = fields.Many2one('hr.employee', 'Zonal Head')
    region_id = fields.Many2one('sales.region', 'Region', compute='_compute_region', store=True)
    margin = fields.Monetary("Margin", compute='_compute_margin', store=True, groups="etl_base.group_sales_margin")
    margin_percent = fields.Float("Margin (%)", compute='_compute_margin', store=True, groups="etl_base.group_sales_margin")
    so_type = fields.Selection([
        ('export', 'Export Sales'),
        ('domestic', 'Domestic Sales'),
        ('direct', 'RTC Sales'),
        ('stock', 'Stock Transfer Sales'),
        ('internal', 'Internal Transfer'),
        ('trade', 'Traded Product Sales'),
        ('rt_sales', 'Retreading Sales'),
        ('service', 'Services'),
        ('foc', 'FOC'),
        ('scrap', 'Scrap Sales'),
        ('seconds', 'Seconds Sales'),
        ('none', 'None')
        ], 'Sales Order Type')
    total_weight = fields.Float('Total Weight', compute='_compute_total_weight', store=True)
    transporter_id = fields.Many2one("eway.transporter", 'Transporter', copy=False, tracking=True)
    booking_dest = fields.Char('Booking Destination')
    fiscal_position_id = fields.Many2one('account.fiscal.position', "Fiscal Position",
        compute='_compute_fiscal_position', store=True, readonly=False)
    fiscal_year = fields.Char('Fiscal Year', compute='_compute_fiscal_year', store=True)
    tag_id = fields.Many2one('crm.tag', 'Tag', compute='_compute_tag', store=True)
    invoice_status = fields.Selection(selection=[
        ('upselling', 'Upselling Opportunity'),
        ('invoiced', 'Fully Invoiced'),
        ('to invoice', 'To Invoice'),
        ('no', 'Nothing to Invoice')],
        string="Invoice Status",
        compute='_compute_invoice_status',
        store=True, tracking=True)
    confirm_button = fields.Selection([('1', 'B1'), ('2', 'B2'), ('3', 'NA')], compute='_compute_confirm_button')
    fully_invoiced = fields.Boolean('Fully Invoiced', tracking=True, copy=False)
    recompute = fields.Boolean()
    
    def _compute_confirm_button(self):
        for order in self:
            if order.state not in ('draft', 'sent'):
                confirm_button = '3'
            else:
                confirm_button = '2'
                if order.amount_total > 50000 and order.l10n_in_gst_treatment == 'unregistered':
                    confirm_button = '1'
            order.confirm_button = confirm_button
            
    def mark_fully_invoiced(self):
        self.fully_invoiced = True
        
    @api.depends('state', 'order_line.invoice_status', 'fully_invoiced')
    def _compute_invoice_status(self):
        unconfirmed_orders = self.filtered(lambda so: so.state not in ['sale', 'done'])
        unconfirmed_orders.invoice_status = 'no'
        confirmed_orders = self - unconfirmed_orders
        if not confirmed_orders:
            return
        line_invoice_status_all = [
            (d['order_id'][0], d['invoice_status'])
            for d in self.env['sale.order.line'].read_group([
                    ('order_id', 'in', confirmed_orders.ids),
                    ('is_downpayment', '=', False),
                    ('display_type', '=', False),
                ],
                ['order_id', 'invoice_status'],
                ['order_id', 'invoice_status'], lazy=False)]
        for order in confirmed_orders:
            if order.fully_invoiced:
                order.invoice_status = 'invoiced'
            else:
                line_invoice_status = [d[1] for d in line_invoice_status_all if d[0] == order.id]
                if order.state not in ('sale', 'done'):
                    order.invoice_status = 'no'
                elif any(invoice_status == 'to invoice' for invoice_status in line_invoice_status):
                    order.invoice_status = 'to invoice'
                elif line_invoice_status and all(invoice_status == 'invoiced' for invoice_status in line_invoice_status):
                    order.invoice_status = 'invoiced'
                elif line_invoice_status and all(invoice_status in ('invoiced', 'upselling') for invoice_status in line_invoice_status):
                    order.invoice_status = 'upselling'
                else:
                    order.invoice_status = 'no'
    
    @api.depends('partner_id', 'partner_id.tag_id')
    def _compute_tag(self):
        for order in self:
            if order.partner_id and order.partner_id.tag_id:
                order.tag_id = order.partner_id.tag_id.id
            else:
                order.tag_id = False
                
    def action_confirm(self):
        res = super(SalesOrder, self).action_confirm()
        for picking in self.picking_ids:
            if picking.state not in ('cancel', 'done'):
                picking.branch_id = self.branch_id.id
                for move in picking.move_ids_without_package:
                    move.branch_id = self.branch_id.id
                    if move.sale_line_id:
                        line = move.sale_line_id
                        move.alt_uom_id = line.alt_uom_id and line.alt_uom_id.id or False
                        move.alt_uom_qty = line.alt_uom_qty
                        move.location_id = picking.picking_type_id.default_location_src_id.id
                picking.do_unreserve()
                picking.location_id = picking.picking_type_id.default_location_src_id.id
        return res
                    
    @api.depends('order_line', 'order_line.product_uom_qty', 'order_line.price_unit', 'validity_date')
    def _compute_margin(self):
        for order in self:
            order.margin = sum([line.margin for line in order.order_line])
            order.margin_percent = order.amount_untaxed and order.margin/order.amount_untaxed or 0
                
    @api.onchange('partner_id')
    def _onchange_partner_id_warning(self):
        res = super(SalesOrder, self)._onchange_partner_id_warning()
        if self.partner_id:
            self.sales_executive_id = self.partner_id.sales_executive_id and self.partner_id.sales_executive_id.id or False
            self.zonal_head_id = self.partner_id.zonal_head_id and self.partner_id.zonal_head_id.id or False
        return res
    
    def _prepare_invoice(self):
        res = super(SalesOrder, self)._prepare_invoice()
        res.update({
            'sales_executive_id': self.sales_executive_id.id,
            'zonal_head_id': self.zonal_head_id.id,
            'transporter_id': self.transporter_id.id,
            'transgst': self.transporter_id.gst,
            'booking_dest': self.booking_dest,
            'so_id': self.id,
            })
        return res
    
    def action_open_discounts(self):
        product_ids = []
        for line in self.order_line:
            if line.product_id:
                product_ids.append(line.product_id.product_tmpl_id.id)
        if product_ids:
            discounts = self.env['sale.discount'].search([('product_ids', 'in', product_ids)])
            for discount in discounts:
                disc_amount = 0
                for line in self.order_line:
                    if line.product_id and line.product_id.product_tmpl_id.id in discount.product_ids.ids:
                        if discount.based_on == 'qty' and line.product_uom_qty >= discount.minimum_value:
                            if discount.type == 'perc':
                                disc_amount += line.price_subtotal * discount.amount * 0.01
                            else:
                                disc_amount += discount.amount
        return True
    
    def action_update_tag(self):
        sos = self.search([])
        for so in sos:
            if so.tag_ids:
                so.tag_id = so.tag_ids[0].id
        return True
    
    def action_update_margin(self):
        sos = self.with_context(no_filter=True).search([])
        for so in sos:
            for line in so.order_line:
                line.recompute = not line.recompute
        return True
    
    @api.model_create_multi
    def create(self, vals_list):
        order = super().create(vals_list)
        prev_orders = self.with_context(no_filter=True).search([
            ('branch_id', '=', order.branch_id.id),
            ('fiscal_year', '=', order.fiscal_year),
            ('id', '!=', order.id),
            ], order='name desc', limit=1)
        if prev_orders:
            prev_name = prev_orders[0].name
            if '/' in prev_name:
                name_split = prev_name.split('/')[-1]
                sequence_number = int(name_split)+1
            else:
                sequence_number = 1
        else:
            sequence_number = 1
        seq_prefix = 'SO/%s/%s'%(order.fiscal_year, order.branch_id.code)
        name = '%s/%s'%(seq_prefix, str(sequence_number).zfill(4))
        order.name = name
        sequence = 1
        for line in order.order_line:
            line.sequence = sequence
            sequence += 1
        return order
    
class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"
    
    def _get_outgoing_incoming_moves(self):
        outgoing_moves = self.env['stock.move']
        incoming_moves = self.env['stock.move']

        moves = self.move_ids.filtered(lambda r: r.state != 'cancel' and not r.scrapped and self.product_id == r.product_id)

        for move in moves:
            if move.picking_id.picking_type_id.code == "outgoing":
                outgoing_moves |= move
            if move.picking_id.picking_type_id.code == "incoming":
                incoming_moves |= move

        return outgoing_moves, incoming_moves
    
    @api.depends('qty_invoiced', 'qty_delivered', 'product_uom_qty', 'state')
    def _compute_qty_to_invoice(self):
        for line in self:
            if line.state in ['sale', 'done'] and not line.display_type:
                if line.product_id.invoice_policy == 'order':
                    line.qty_to_invoice = line.product_uom_qty - line.qty_invoiced
                    line.alt_uom_qty_toinvoice = line.alt_uom_qty - line.alt_uom_qty_invoiced
                else:
                    line.qty_to_invoice = line.qty_delivered - line.qty_invoiced
                    line.alt_uom_qty_toinvoice = line.alt_uom_qty_delivered - line.alt_uom_qty_invoiced
            else:
                line.qty_to_invoice = 0
                line.alt_uom_qty_toinvoice = 0
                
    @api.depends('invoice_lines.move_id.state', 'invoice_lines.quantity')
    def _compute_qty_invoiced(self):
        for line in self:
            qty_invoiced, alt_uom_qty_invoiced = 0.0, 0
            for invoice_line in line._get_invoice_lines():
                if invoice_line.move_id.state != 'cancel' or invoice_line.move_id.payment_state == 'invoicing_legacy':
                    if invoice_line.move_id.move_type == 'out_invoice':
                        qty_invoiced += invoice_line.product_uom_id._compute_quantity(invoice_line.quantity, line.product_uom)
                        alt_uom_qty_invoiced += invoice_line.alt_uom_qty
                    elif invoice_line.move_id.move_type == 'out_refund':
                        qty_invoiced -= invoice_line.product_uom_id._compute_quantity(invoice_line.quantity, line.product_uom)
                        alt_uom_qty_invoiced -= invoice_line.alt_uom_qty
            line.qty_invoiced = qty_invoiced
            line.alt_uom_qty_invoiced = alt_uom_qty_invoiced
            
    def _compute_qty_delivered(self):
        for line in self:
            margin_actual, unit_cost_actual = 0.0, 0.0
            qty, alt_uom_qty = 0.0, 0
            outgoing_moves, incoming_moves = line._get_outgoing_incoming_moves()
            for move in outgoing_moves:
                if move.state != 'done':
                    continue
                qty += move.product_uom._compute_quantity(move.quantity_done, line.product_uom, rounding_method='HALF-UP')
                alt_uom_qty += move.alt_uom_qty_actual
            for move in incoming_moves:
                if move.state != 'done':
                    continue
                qty -= move.product_uom._compute_quantity(move.quantity_done, line.product_uom, rounding_method='HALF-UP')
                alt_uom_qty -= move.alt_uom_qty_actual
            
            line.qty_delivered = qty
            line.alt_uom_qty_delivered = alt_uom_qty
            
            price_reduce = round(line.price_reduce, 3)
            if line.product_id:
                unit_cost_actual = line.get_product_outprice()
            margin_actual = round(price_reduce - unit_cost_actual, 3)
            line.margin_actual = margin_actual
            line.unit_cost_actual = unit_cost_actual
    
    def get_product_outprice(self):
        unit_cost = 0.0
        moves = self.env['stock.move'].search([
            ('sale_line_id', '=', self.id),
            ('picking_id.state', '=', 'done'),
            ('product_id', '=', self.product_id.id)
            ], order='date desc')
        if moves:
            total_cost, total_qty = 0.0, 0.0
            for move in moves:
                total_cost += move.price_unit * move.quantity_done
                total_qty += move.quantity_done
            if total_qty > 0:
                unit_cost = round(total_cost / total_qty, 3)
        return round(unit_cost, 3)
    
    @api.depends('price_unit', 'product_id', 'discount_value', 'discount', 'order_id.recompute', 'order_id.date_order')
    def _compute_purchase_price(self):
        for line in self:
            dp_dic = {2: 0.01, 3: 0.001}
            invoice_decimal = 2
            if line.order_id and line.order_id.partner_id:
                if line.order_id.partner_id.is_branch:
                    invoice_decimal = 3
                else:
                    if line.order_id.partner_id.invoice_decimal:
                        invoice_decimal = line.order_id.partner_id.invoice_decimal
                    else:
                        invoice_decimal = False
            dp = dp_dic[invoice_decimal]
            purchase_price = 0.0
            price_unit = line.price_unit * (1 - 0.01 * line.discount)
            price_unit = round(tools.float_round(price_unit, precision_rounding=dp), invoice_decimal)
            price_unit_disc = price_unit - line.discount_value
            line_discount_price_unit = round(tools.float_round(price_unit_disc, precision_rounding=dp), invoice_decimal)
            line.price_reduce = line_discount_price_unit
            if line.product_id:
                purchase_price = line.get_product_inprice()
            line.purchase_price = purchase_price
            margin = round(line_discount_price_unit - purchase_price, 3)
            line.margin = margin
            margin_percent = 0.0
            if purchase_price > 0:
                margin_percent = round(margin/purchase_price, 3)*100
            line.margin_percent = margin_percent
    
    def get_product_inprice(self):
        unit_price = 0.0
        svls = self.env['stock.valuation.layer'].search([
            ('create_date', '<=', self.order_id.date_order),
            ('branch_id', '=', self.order_id.branch_id.id),
            ('product_id', '=', self.product_id.id),
            ('quantity', '>', 0)
            ], order='create_date desc')
        if svls:
            unit_price = svls[0].unit_cost
        else:
            unit_price = self.product_id.standard_price
        return round(unit_price, 3)
    
    @api.onchange('product_id', 'alt_uom_id', 'alt_uom_qty')
    def onchange_alt_uom(self):
        if self.product_id and self.alt_uom_id:
            template = self.product_id.product_tmpl_id
            if self.alt_uom_id.type == 'base':
                self.product_uom_qty = template.weight_bag * self.alt_uom_qty
            elif self.alt_uom_id.type == 'smaller':
                self.product_uom_qty = template.weight_belt * self.alt_uom_qty
        else:
            self.product_uom_qty = 0
    
    @api.depends('display_type', 'product_id', 'product_packaging_qty')
    def _compute_product_uom_qty(self):
        for line in self:
            if line.display_type:
                line.product_uom_qty = 0.0
                continue

            if not line.product_packaging_id:
                continue
            packaging_uom = line.product_packaging_id.product_uom_id
            qty_per_packaging = line.product_packaging_id.qty
            product_uom_qty = packaging_uom._compute_quantity(
                line.product_packaging_qty * qty_per_packaging, line.product_uom)
            if float_compare(product_uom_qty, line.product_uom_qty, precision_rounding=line.product_uom.rounding) != 0:
                line.product_uom_qty = product_uom_qty
    
    @api.depends('alt_uom_id', 'alt_uom_qty')
    def _compute_bag_qty(self):
        for line in self:
            if line.product_id and line.alt_uom_id and line.alt_uom_id.type == 'base':
                line.belt_qty = line.alt_uom_qty * line.product_id.belt_no
            else:
                line.belt_qty = line.alt_uom_qty
    
    def _check_editing_access(self):
        if self.user_has_groups('etl_base.group_soprice_editing'):
            return True
        else:
            return False
        
    qty_delivered = fields.Float("Delivered Quantity", compute='_compute_qty_delivered',
        digits='Product Unit of Measure', readonly=False, copy=False)
    qty_invoiced = fields.Float("Invoiced Quantity", compute='_compute_qty_invoiced',
        digits='Product Unit of Measure', store=True)
    qty_to_invoice = fields.Float("Quantity To Invoice", compute='_compute_qty_to_invoice',
        digits='Product Unit of Measure', store=True)
    alt_uom_id = fields.Many2one('product.alt.uom', 'Package Name')
    alt_uom_qty = fields.Integer('Package Qty', default=1)
    belt_qty = fields.Integer('Belt Qty', compute='_compute_bag_qty', store=True)
    alt_uom_qty_delivered = fields.Integer('Package Qty (Delivered)', compute='_compute_qty_delivered')
    alt_uom_qty_invoiced = fields.Integer('Package Qty (Invoiced)', compute='_compute_qty_invoiced')
    alt_uom_qty_toinvoice = fields.Integer('Package Qty (To Invoice)', compute='_compute_qty_to_invoice')
    margin = fields.Float("Margin", compute='_compute_purchase_price', 
        digits='Product Price', groups="etl_base.group_sales_margin", store=True)
    margin_percent = fields.Float("Margin (%)", compute='_compute_purchase_price', 
        groups="etl_base.group_sales_margin", store=True)
    purchase_price = fields.Float("Unit Cost", compute="_compute_purchase_price",
        digits='Product Price', readonly=False, 
        groups="etl_base.group_sales_margin", store=True)
    margin_actual = fields.Float("Actual Margin", compute='_compute_qty_delivered',
        digits='Product Price', groups="etl_base.group_sales_margin")
    unit_cost_actual = fields.Float("Actual Unit Cost", compute="_compute_qty_delivered",
        digits='Product Price', readonly=False,
        groups="etl_base.group_sales_margin")
    discount_value = fields.Float('Discount/KG')
    price_reduce = fields.Float("Unit Price After Discount", compute='_compute_purchase_price',
        digits=(16,4), store=True)
    price_subtotal = fields.Monetary("Subtotal", compute='_compute_amount', store=True)
    price_tax = fields.Float("Total Tax", compute='_compute_amount', store=True)
    price_total = fields.Monetary("Total", compute='_compute_amount', store=True)
    price_reduce_taxexcl = fields.Monetary("Price Reduce Tax excl",
        compute='_compute_price_reduce_taxexcl', store=True, precompute=True)
    price_reduce_taxinc = fields.Monetary("Price Reduce Tax incl", 
        compute='_compute_price_reduce_taxinc', store=True, precompute=True)
    product_uom_qty = fields.Float("Gross Weight", compute='_compute_product_uom_qty',
        digits='Product Unit of Measure', default=1.0,
        store=True, readonly=False, required=True, precompute=True)
    product_group1_id = fields.Many2one('product.group1', 'Product Group1', compute='_compute_product_group', store=True)
    product_group2_id = fields.Many2one('product.group2', 'Product Group2', compute='_compute_product_group', store=True)
    product_group3_id = fields.Many2one('product.group3', 'Product Group3', compute='_compute_product_group', store=True)
    remarks = fields.Char('Remarks')
    tax_id = fields.Many2many('account.tax', string="Taxes",
        compute='_compute_tax_id', store=True, readonly=False, precompute=True,
        context={'active_test': False}, check_company=True)
    invoice_status = fields.Selection([
            ('upselling', "Upselling Opportunity"),
            ('invoiced', "Fully Invoiced"),
            ('to invoice', "To Invoice"),
            ('no', "Nothing to Invoice"),
            ],
        "Invoice Status", compute='_compute_invoice_status', store=True)
    sequence = fields.Integer(string="Sequence", default=1)
    sl_no = fields.Integer("SL No.", compute='_compute_sl_no', store=True)
    recompute = fields.Boolean()
    allow_unitprice_editing = fields.Boolean('Allow UnitPrice Editing', compute='_check_unitprice_access',
        default=_check_editing_access)
    
    def _check_unitprice_access(self):
        for line in self:
            allow_editing = False
            if self.user_has_groups('etl_base.group_soprice_editing'):
                allow_editing = True
            line.allow_unitprice_editing = allow_editing
            
    @api.depends('sequence')
    def _compute_sl_no(self):
        for line in self:
            line.sl_no = line.sequence
        
    @api.depends('state', 'product_uom_qty', 'qty_delivered', 'qty_to_invoice', 'qty_invoiced')
    def _compute_invoice_status(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            if line.state not in ('sale', 'done'):
                line.invoice_status = 'no'
            elif line.is_downpayment and line.untaxed_amount_to_invoice == 0:
                line.invoice_status = 'invoiced'
            elif not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                line.invoice_status = 'to invoice'
            elif line.state == 'sale' and line.product_id.invoice_policy == 'order' and\
                    line.product_uom_qty >= 0.0 and\
                    float_compare(line.qty_delivered, line.product_uom_qty, precision_digits=precision) == 1:
                line.invoice_status = 'upselling'
            elif float_compare(line.qty_invoiced, line.product_uom_qty, precision_digits=precision) >= 0:
                line.invoice_status = 'invoiced'
            else:
                line.invoice_status = 'no'
                
    @api.depends('product_id', 'order_id.fiscal_position_id', 'order_id.partner_id', 'order_id.partner_id.tcs_ok')
    def _compute_tax_id(self):
        company = self.env['res.company'].browse(1)
        taxes_by_product_company = defaultdict(lambda: self.env['account.tax'])
        lines_by_company = defaultdict(lambda: self.env['sale.order.line'])
        cached_taxes = {}
        for line in self:
            lines_by_company[line.company_id] += line
        for product in self.product_id:
            for tax in product.taxes_id:
                taxes_by_product_company[(product, tax.company_id)] += tax
        for company, lines in lines_by_company.items():
            for line in lines.with_company(company):
                taxes = taxes_by_product_company[(line.product_id, company)]
                if not line.product_id or not taxes:
                    # Nothing to map
                    line.tax_id = False
                    continue
                fiscal_position = line.order_id.fiscal_position_id
                cache_key = (fiscal_position.id, company.id, tuple(taxes.ids))
                if cache_key in cached_taxes:
                    result = cached_taxes[cache_key]
                else:
                    result = fiscal_position.map_tax(taxes)
                    cached_taxes[cache_key] = result
                # If company_id is set, always filter taxes by the company
                if line.order_id.partner_id.tcs_ok:
                    result = self.env['account.tax'].browse([result.id, company.tcs_tax_id.id])
                line.tax_id = result
    
    @api.depends('product_id', 'product_id.product_tmpl_id.product_group1_id', 'product_id.product_tmpl_id.product_group2_id', 'product_id.product_tmpl_id.product_group3_id')
    def _compute_product_group(self):
        for line in self:
            group1_id, group2_id, group3_id = False, False, False
            if line.product_id:
                group1_id = line.product_id.product_group1_id and line.product_id.product_group1_id.id or False
                group2_id = line.product_id.product_group2_id and line.product_id.product_group2_id.id or False
                group3_id = line.product_id.product_group3_id and line.product_id.product_group3_id.id or False
            line.product_group1_id = group1_id
            line.product_group2_id = group2_id
            line.product_group3_id = group3_id
                
    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id', 'discount_value')
    def _compute_amount(self):
        for line in self:
            tax_results = self.env['account.tax']._compute_taxes([line._convert_to_tax_base_line_dict()])
            totals = list(tax_results['totals'].values())[0]
            amount_untaxed = totals['amount_untaxed']
            amount_tax = totals['amount_tax']

            line.update({
                'price_subtotal': amount_untaxed,
                'price_tax': amount_tax,
                'price_total': amount_untaxed + amount_tax,
                })
    
    def _convert_to_tax_base_line_dict(self):
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=self.product_id,
            taxes=self.tax_id,
            price_unit=self.price_reduce,
            quantity=self.product_uom_qty,
            discount=0,
            price_subtotal=self.price_subtotal)
    
    @api.depends('price_subtotal', 'product_uom_qty', 'discount_value')
    def _compute_price_reduce_taxexcl(self):
        for line in self:
            line.price_reduce_taxexcl = line.price_subtotal / line.product_uom_qty if line.product_uom_qty else 0.0

    @api.depends('price_total', 'product_uom_qty', 'discount_value')
    def _compute_price_reduce_taxinc(self):
        for line in self:
            line.price_reduce_taxinc = line.price_total / line.product_uom_qty if line.product_uom_qty else 0.0
            
    def _convert_price(self, product_cost, from_uom):
        self.ensure_one()
        if not product_cost:
            if not self.purchase_price:
                return product_cost
        from_currency = self.product_id.cost_currency_id
        to_cur = self.currency_id or self.order_id.currency_id
        to_uom = self.product_uom
        if to_uom and to_uom != from_uom:
            product_cost = from_uom._compute_price(
                product_cost,
                to_uom,
            )
        return from_currency._convert(
            from_amount=product_cost,
            to_currency=to_cur,
            company=self.company_id or self.env.company,
            date=self.order_id.date_order or fields.Date.today(),
            round=False,
        ) if to_cur and product_cost else product_cost
    
    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleOrderLine, self)._prepare_invoice_line()
        res.update({
            'discount_value': self.discount_value,
            'alt_uom_id': self.alt_uom_id and self.alt_uom_id.id or False,
            'alt_uom_qty': self.alt_uom_qty_toinvoice
            })
        return res

    
class SalesDiscount(models.Model):
    _name = 'sale.discount'
    _description = 'Sales Discount'
    
    name = fields.Char('Description', required=True)

class SaleReport(models.Model):
    _inherit = "sale.report"

    sales_executive_id = fields.Many2one('hr.employee', 'Sales Executive')
    zonal_head_id = fields.Many2one('hr.employee', 'Zonal Head')
    region_id = fields.Many2one('sales.region', 'Region')
    product_group1_id = fields.Many2one('product.group1', 'Product Group1')
    product_group2_id = fields.Many2one('product.group2', 'Product Group2')
    product_group3_id = fields.Many2one('product.group3', 'Product Group3')
    so_type = fields.Selection([
        ('export', 'Export Sales'),
        ('domestic', 'Domestic Sales'),
        ('direct', 'RTC Sales'),
        ('stock', 'Stock Transfer Sales'),
        ('internal', 'Internal Transfer'),
        ('trade', 'Traded Product Sales'),
        ('rt_sales', 'Retreading Sales'),
        ('foc', 'FOC'),
        ('scrap', 'Scrap Sales'),
        ('seconds', 'Seconds Sales'),
        ('none', 'None')
        ], 'Sales Order Type')
    tag_id = fields.Many2one('crm.tag', 'Tag')
    
    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['sales_executive_id'] = "s.sales_executive_id"
        res['zonal_head_id'] = "s.zonal_head_id"
        res['region_id'] = "s.region_id"
        res['so_type'] = "s.so_type"
        res['tag_id'] = "s.tag_id"
        res['product_group1_id'] = "l.product_group1_id"
        res['product_group2_id'] = "l.product_group2_id"
        res['product_group3_id'] = "l.product_group3_id"
        
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += """,
            s.sales_executive_id,
            s.zonal_head_id,
            s.region_id,
            s.so_type,
            s.tag_id,
            l.product_group1_id,
            l.product_group2_id,
            l.product_group3_id
            """
        return res
