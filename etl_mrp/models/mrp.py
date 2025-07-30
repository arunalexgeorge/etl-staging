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
from odoo.tools import format_datetime
from odoo.tools import float_round
from collections import defaultdict
from odoo.tools.misc import OrderedSet, format_date, groupby as tools_groupby
from datetime import datetime, timedelta
rec = 0
import logging
from asyncio.base_events import ssl
logger = logging.getLogger(__name__)

def autoIncrement():
    global rec
    pStart = 1
    pInterval = 1
    if rec == 0:
        rec = pStart
    else:
        rec += pInterval
    return rec

class MrpConsumptionWarning(models.TransientModel):
    _inherit = 'mrp.consumption.warning'

    def action_set_qty(self):
        self.mrp_production_ids.action_assign()
        return self.action_confirm()

class MrpUnbuild(models.Model):
    _inherit = "mrp.unbuild"
    
    def action_rm_unbuild(self):
        ml_obj = self.env['stock.move.line']
        un_move_lines = ml_obj.search([('move_id.consume_unbuild_id', '=', self.id)])
        if un_move_lines:
            svls = self.env['stock.valuation.layer'].search([('move_line_id', 'in', un_move_lines.ids)])
            if svls:
                svls.delete_svl_sm_am()
            else:
                for un_move_line in un_move_lines:
                    self._cr.execute('delete from stock_move where id=%s'% (un_move_line.move_id.id))
                    self._cr.execute('delete from stock_move_line where id=%s'% (un_move_line))
            
        move_lines = ml_obj.search([('move_id.raw_material_production_id', '=', self.mo_id.id)])
        self.action_create_unbuild_move(move_lines, consume_unbuild_id=self.id)
        return True
    
    def action_fm_unbuild(self):
        ml_obj = self.env['stock.move.line']
        un_move_lines = ml_obj.search([('move_id.unbuild_id', '=', self.id)])
        if un_move_lines:
            svls = self.env['stock.valuation.layer'].search([('move_line_id', 'in', un_move_lines.ids)])
            if svls:
                svls.delete_svl_sm_am()
            else:
                for un_move_line in un_move_lines:
                    self._cr.execute('delete from stock_move where id=%s'% (un_move_line.move_id.id))
                    self._cr.execute('delete from stock_move_line where id=%s'% (un_move_line))
        move_lines = ml_obj.search([('move_id.production_id', '=', self.mo_id.id)])
        self.action_create_unbuild_move(move_lines, unbuild_id=self.id)
        for line in self.mo_id.serial_line_ids:
            serial = line.serial_id
            if serial and serial.quantity > 0:
                for sl in serial.loc_line_ids:
                    self.env['stock.serial.line'].create({
                        'location_id': sl.location_id.id,
                        'location_dest_id': self.company_id.unbuild_location_id.id,
                        'date': fields.Datetime.now(),
                        'quantity': sl.quantity,
                        'serial_id': serial.id
                        }).id
            serial.action_create_sl()
        return True
    
    def action_create_unbuild_move(self, mrp_move_lines, unbuild_id=False, consume_unbuild_id=False):
        for move_line in mrp_move_lines:
            move_lines = [(0, 0, {
                'location_id': move_line.location_dest_id.id, 
                'location_dest_id': move_line.location_id.id,
                'lot_id': move_line.lot_id.id,
                'qty_done': move_line.qty_done,
                'branch_id': move_line.branch_id.id,
                'state': 'draft',
                'picking_id': False,
                'product_id': move_line.product_id.id,
                'product_uom_id': move_line.product_uom_id.id,
                'reference': self.name,
                'unit_cost': move_line.unit_cost
                })]
            new_move = self.env['stock.move'].create({
                'location_id': move_line.location_dest_id.id, 
                'location_dest_id': move_line.location_id.id,
                'picking_id': False,
                'group_id': False,
                'purchase_line_id': False,
                'branch_id': move_line.branch_id.id,
                'quantity_done': move_line.qty_done,
                'state': 'confirmed',
                'product_id': move_line.product_id.id,
                'product_uom': move_line.product_uom_id.id,
                'product_uom_qty': move_line.qty_done,
                'name': self.name,
                'move_line_ids': move_lines,
                'price_unit': move_line.unit_cost,
                'unbuild_id': unbuild_id and unbuild_id or False,
                'consume_unbuild_id': consume_unbuild_id and consume_unbuild_id or False
                })
            new_move._action_done()
        return True
    
    def action_unbuild(self):
        self.ensure_one()
        if self.mo_id:
            if self.mo_id.state != 'done':
                raise UserError('You cannot unbuild a undone manufacturing order.')
        self.action_fm_unbuild()
        self.action_rm_unbuild()
        if self.mo_id:
            unbuild_msg = _(
                "%(qty)s %(measure)s unbuilt in %(order)s",
                qty=self.product_qty,
                measure=self.product_uom_id.name,
                order=self._get_html_link(),
            )
            self.mo_id.message_post(
                body=unbuild_msg,
                subtype_id=self.env.ref('mail.mt_note').id)
        return self.write({'state': 'done'})
    
class Picking(models.Model):
    _inherit = 'stock.picking'
    
    git_production_id = fields.Many2one('mrp.production', 'GIT MO')
    wip_production_id = fields.Many2one('mrp.production', 'WIP MO')
    
    def button_validate(self):
        res = super(Picking, self).button_validate()
        for picking in self:
            if picking.git_production_id:
                picking.git_production_id.with_context(mrp_assign=True).action_assign()
        return res
    
class MrpSerial(models.Model):
    _name = 'mrp.serial'
    _description = 'MRP Serial'
    
    @api.depends('state_manual', 'quantity', 'tolerance', 'weight_bag')
    def _compute_status(self):
        for line in self:
            line.state = line.state_manual
    
    @api.onchange('quantity')
    def onchange_quantity(self):
        qty_min = round(self.weight_bag, 3) - round(self.tolerance, 3)
        qty_max = round(self.weight_bag, 3) + round(self.tolerance, 3)
        if round(self.quantity, 3) >= qty_min and self.quantity <= qty_max:
            self.state_manual = 'approved'
        else:
            self.state_manual = 'waiting'
    
    def action_approve(self):
        self.state_manual = 'approved'
        self.production_id.qty_producing = sum([serial.quantity for serial in self.production_id.serial_line_ids if serial.state == 'approved'])
        return True
    
    def action_reject(self):
        self.state_manual = 'rejected'
        self.production_id.qty_producing = sum([serial.quantity for serial in self.production_id.serial_line_ids if serial.state == 'approved'])
        return True
    
    def _compute_mrp(self):
        for line in self:
            line.mrp = line.quantity * line.production_id.product_id.MRP_product
    
    def action_print_label(self):
        if self.production_id.state != 'done':
            raise UserError('MO should be in Done Status for printing label')
        if self.state != 'approved':
            raise UserError('Serial Number should be in Approved Status for printing')
        if not self.production_id.lot_producing_id:
            self.production_id.create_auto_lot()
        return self.env.ref('etl_mrp.action_serial_number_label').report_action(self)
    
    name = fields.Char('Serial No.')
    quantity = fields.Float('Weight')
    production_id = fields.Many2one('mrp.production', 'MO')
    serial_id = fields.Many2one('stock.serial', 'Serial No')
    serial_line_id = fields.Many2one('stock.serial.line', 'Serial Line')
    currency_id = fields.Many2one('res.currency', related='production_id.company_id.currency_id')
    tolerance = fields.Float('Tolerance', digits=(16, 3))
    weight_bag = fields.Float('Gross Weight')
    state = fields.Selection([
        ('waiting', 'Waiting Approval'), 
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
        ], 'Status', compute='_compute_status', store=True)
    state_manual = fields.Selection([
        ('waiting', 'Waiting Approval'), 
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
        ], 'Manual Status')
    mrp = fields.Monetary('MRP', compute='_compute_mrp')
    
    def get_pound(self, quantity):
        pound_qty = '%s (%s KG)'%(str(round(quantity * 2.20462, 3)), str(quantity))
        return pound_qty
    
class BomLine(models.Model):
    _inherit = 'mrp.bom.line'
    
    def _login_user(self):
        for mo in self:
            mo.login_user_id = self.env.user.id
            
    alt_product_ids = fields.Many2many('product.product', string='Alternate Products')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
        
class Production(models.Model):
    _inherit = 'mrp.production'
    _order = 'date_planned_start desc'
    
    def action_view_stock_valuation_layers(self):
        res = super(Production, self).action_view_stock_valuation_layers()
        for mrp in self:
            if mrp.unit_cost == 0:
                mrp.mrp_svl_correction()
        return res
    
    def _get_consumption_issues(self):
        for production in self:
            for move in production.move_raw_ids:
                if move.current_stock < move.product_uom_qty:
                    raise UserError('Stock not available for %s'%(move.product_id.name_get()[0][1]))
        return False
    
    @api.onchange('batch_qty')
    def onchange_batchqty(self):
        if self.batch_qty and self.bom_id:
            self.product_qty = self.batch_qty * self.bom_id.product_qty
    
    @api.depends('product_id', 'product_id.categ_id', 'product_id.categ_id.category_type')
    def _compute_product_details(self):
        for mrp in self:
            if mrp.product_id:
                if mrp.product_id.categ_id.category_type == 'fg':
                    mrp.fg = True
                else:
                    mrp.fg = False
                mrp.categ_id = mrp.product_id.categ_id.id
            else:
                mrp.categ_id = False
    
    def _compute_curing(self):
        for mrp in self:
            if mrp.product_id and mrp.product_id.curing_ok:
                mrp.curing = True
            else:
                mrp.curing = False
                
    def _compute_git_count(self): 
        for mrp in self:
            mrp.git_picking_count = len([picking.id for picking in mrp.git_picking_ids])
    
    def _compute_wip_count(self): 
        for mrp in self:
            mrp.wip_picking_count = len([picking.id for picking in mrp.wip_picking_ids])
            
    def _get_stock_request_state(self):
        for mrp in self:
            if any(picking.state != 'done' for picking in mrp.git_picking_ids):
                state = 'draft'
            else:
                state = 'done'
            mrp.stock_request_state = state
    
    def _get_stock_accept_state(self):
        for mrp in self:
            if any(picking.state != 'done' for picking in mrp.wip_picking_ids):
                state = 'draft'
            else:
                state = 'done'
            mrp.stock_accept_state = state
    
    def _compute_picking_type_id(self):
        wh = self.env['stock.warehouse'].search([('branch_id', '=', self.env.user.branch_id.id)])
        if wh:
            return wh[0].manu_type_id.id
    
    def _compute_srb(self):
        for mo in self:
            srb = False
            pending_requests = False
            for git_picking in mo.git_picking_ids:
                if git_picking.state != 'done':
                    pending_requests = True
                    break
            if mo.state in ('confirmed', 'progress') and not pending_requests:
                srb = True
            mo.show_request_button = srb
    
    def action_print_label(self):
        if self.state != 'done':
            raise UserError('MO should be in Done Status for printing label')
        if self.serial_line_ids:
            serial_lines = []
            for line in self.serial_line_ids:
                if line.state == 'approved':
                    serial_lines.append(line.id)
            if serial_lines:
                serials = self.env['mrp.serial'].browse(serial_lines)
                return self.env.ref('etl_mrp.action_serial_number_label').report_action(serials)
        else:
            return True
    
    @api.depends('product_id', 'product_id.product_tmpl_id.product_group1_id', 'product_id.product_tmpl_id.product_group2_id', 'product_id.product_tmpl_id.product_group3_id')
    def _compute_product_group(self):
        for mrp in self:
            group1_id, group2_id, group3_id = False, False, False
            if mrp.product_id:
                product = mrp.product_id
                group1_id = product.product_group1_id and product.product_group1_id.id or False
                group2_id = product.product_group2_id and product.product_group2_id.id or False
                group3_id = product.product_group3_id and product.product_group3_id.id or False
            mrp.product_group1_id = group1_id
            mrp.product_group2_id = group2_id
            mrp.product_group3_id = group3_id
    
    def _login_user(self):
        for mo in self:
            mo.login_user_id = self.env.user.id
    
    def _compute_unitcost(self):
        for mo in self:
            unit_cost = 0.0
            if mo.state == 'done':
                unit_cost = mo.move_finished_ids and \
                    mo.move_finished_ids[0].stock_valuation_layer_ids and \
                    mo.move_finished_ids[0].stock_valuation_layer_ids[0].unit_cost
            mo.unit_cost = unit_cost
    
    def _compute_fg_move_count(self):
        for mo in self:
            mo.fg_move_count = len(mo.move_finished_ids.ids)
        
    is_export = fields.Boolean('Is Export?')
    label_type = fields.Selection([
        ('local', 'Local'), 
        ('export', 'Export'), 
        ('export_us', 'Export(US)')
        ], 'Label Type', default='local')
    batch_qty = fields.Integer('No.of Batches/Bags/Belts', default=1)
    serial_line_ids = fields.One2many('mrp.serial', 'production_id', 'Serial Numbers', copy=False)
    shift_line_ids = fields.One2many('mrp.shift.line', 'production_id', 'Curing Shifts', copy=False)
    lot_producing_id = fields.Many2one('stock.lot', 'Lot Number', copy=False,
        domain="[('product_id', '=', product_id)]", check_company=True)
    serial_ok = fields.Boolean('Serial No Generated', copy=False)
    fg = fields.Boolean('FG', compute='_compute_product_details', store=True)
    categ_id = fields.Many2one('product.category', 'Product Category', compute='_compute_product_details', store=True)
    product_group1_id = fields.Many2one('product.group1', 'Product Group1', compute='_compute_product_group', store=True)
    product_group2_id = fields.Many2one('product.group2', 'Product Group2', compute='_compute_product_group', store=True)
    product_group3_id = fields.Many2one('product.group3', 'Product Group3', compute='_compute_product_group', store=True)
    curing = fields.Boolean('Curing SFG', compute='_compute_curing')
    git_picking_ids = fields.One2many('stock.picking', 'git_production_id', 'Stock Requests', domain=[('state', '!=', 'cancel')])
    wip_picking_ids = fields.One2many('stock.picking', 'wip_production_id', 'Stock Receipts', domain=[('state', '!=', 'cancel')])
    stock_request_state = fields.Selection([('draft', 'Pending'), ('done', 'Completed')], 'Request Status',
        compute='_get_stock_request_state')
    stock_accept_state = fields.Selection([('draft', 'Pending'), ('done', 'Completed')], 'Accept Status',
        compute='_get_stock_accept_state')
    git_picking_count = fields.Integer('GIT Count', compute='_compute_git_count')
    wip_picking_count = fields.Integer('WIP Count', compute='_compute_wip_count')
    shift1 = fields.Float('Shift 1')
    shift2 = fields.Float('Shift 2')
    shift3 = fields.Float('Shift 3')
    picking_type_id = fields.Many2one(
        'stock.picking.type', 'Operation Type', copy=True, readonly=False,
        default=_compute_picking_type_id,
        domain="[('code', '=', 'mrp_operation'), ('company_id', '=', company_id)]",
        required=True, check_company=True, index=True)
    location_src_id = fields.Many2one(
        'stock.location', 'Components Location',
        compute='_compute_locations_new', store=True, check_company=True,
        readonly=False, required=True, precompute=True,
        domain="[('usage','=','internal'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Location where the system will look for components.")
    location_dest_id = fields.Many2one(
        'stock.location', 'Finished Products Location',
        compute='_compute_locations_new', store=True, check_company=True,
        readonly=False, required=True, precompute=True,
        domain="[('usage','=','internal'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Location where the system will stock the finished products.")
    show_request_button = fields.Boolean('SRB', compute='_compute_srb')
    rejection_picking_id = fields.Many2one('stock.picking', 'MO Rejection IM')
    conversion_cost = fields.Float('Conversion Cost')
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    unit_cost = fields.Float('Unit Cost', digits=(16, 3), compute='_compute_unitcost')
    fg_move_count = fields.Integer('FG Move Count', compute='_compute_fg_move_count')
    
    @api.depends('picking_type_id', 'product_id')
    def _compute_locations_new(self):
        for production in self:
            production.location_src_id = production.picking_type_id.default_location_src_id.id
            if production.product_id.categ_id.category_type == 'fg' and production.product_id.categ_id.production_location_id:
                location_dest_id = production.product_id.categ_id.production_location_id
            else:
                location_dest_id  = production.picking_type_id.default_location_dest_id.id
            production.location_dest_id = location_dest_id
    
    def action_open_wips(self):
        pickings = self.wip_picking_ids

        self.ensure_one()
        result = self.env["ir.actions.actions"]._for_xml_id('stock.action_picking_tree_all')
        result['context'] = {'default_picking_type_id': self.company_id.factory_gitwip_id.id}
        if not pickings or len(pickings) > 1:
            result['domain'] = [('id', 'in', pickings.ids)]
        elif len(pickings) == 1:
            res = self.env.ref('stock.view_picking_form', False)
            form_view = [(res and res.id or False, 'form')]
            result['views'] = form_view + [(state, view) for state, view in result.get('views', []) if view != 'form']
            result['res_id'] = pickings.id
        return result
    
    def action_open_gits(self):
        return True
    
    def action_request_stock(self):
        products_dic = {}
        for move in self.move_raw_ids:
            if round(move.current_stock, 3) < round(move.product_uom_qty, 3):
                products_dic.update({move.product_id: round(move.product_uom_qty,3)-round(move.current_stock,3)})
        picking = False
        for product in products_dic:
            picking_type = self.company_id.factory_rmgit_id
            if not picking:
                picking = self.env['stock.picking'].create({
                    'picking_type_id': picking_type.id,
                    'location_id': picking_type.default_location_src_id.id, 
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'git_production_id': self.id,
                    'origin': self.name,
                    'company_id': self.env.user.company_id.id
                    })
                picking_id = picking.id
            self.env['stock.move'].create({
                'location_id': picking_type.default_location_src_id.id, 
                'location_dest_id': picking_type.default_location_dest_id.id,
                'picking_id': picking_id,
                'product_id': product.id,
                'name': product.name_get()[0][1],
                'product_uom_qty': products_dic[product],
                'product_uom': product.uom_id.id
                })
        if picking:
            picking.action_confirm()
            picking.with_context(sfgrm_assign=True).action_assign()
        return True

    def button_generate_sns(self):
        if not self.product_id.serial_sequence_id:
            raise UserError('Configure Serial Number Sequence for %s'%(self.product_id.name))
        if not self.serial_line_ids:
            for i in range(self.batch_qty):
                sl_vals = {
                    'name': self.product_id.serial_sequence_id.next_by_id(),
                    'production_id': self.id,
                    'weight_bag': self.product_id.weight_bag,
                    'tolerance': self.product_id.tolerance
                    }
                if self.product_id.categ_id.fg_type != 'pctr':
                    sl_vals.update({
                        'quantity': self.product_id.weight_bag,
                        'state_manual': 'approved',
                        'state': 'approved'
                        })
                self.env['mrp.serial'].create(sl_vals)
        self.serial_ok = True
        return True

    @api.onchange('serial_line_ids')
    def onchange_serial_ids(self): 
        self.qty_producing = sum([serial.quantity for serial in self.serial_line_ids if serial.state == 'approved'])
    
    def create_auto_lot(self):
        lot_dic = {}
        lot_obj = self.env['stock.lot']
        for move in self.move_raw_ids:
            if move.product_id.categ_id.category_type == 'sfg':
                for line in move.move_line_ids:
                    if line.lot_id:
                        lot_dic.update({line.lot_id.name: line.qty_done})
        sortedDict = sorted(lot_dic.items(), key=lambda x:x[1])
        if sortedDict:
            lot_name = sortedDict[-1][0]
            if self.lot_producing_id and self.lot_producing_id.name == lot_name:
                pass
            else:
                lots = lot_obj.search([
                    ('name', '=', lot_name),
                    ('product_id', '=', self.product_id.id)
                    ])
                if lots:
                    self.lot_producing_id = lots[0].id
                else:
                    self.lot_producing_id = lot_obj.create({
                        'product_id': self.product_id.id,
                        'company_id': self.company_id.id,
                        'name': lot_name
                        })
        return True

    def create_serial_numbers(self):
        sl_obj = self.env['stock.serial']
        ssl = self.env['stock.serial.line']
        for mrp in self:
            for serial in mrp.serial_line_ids:
                serial_id = False
                if serial.serial_id:
                    vals = {
                        'lot_id': mrp.lot_producing_id.id,
                        'name': serial.name,
                    }
                    if not serial.serial_id.date:
                        vals['date'] = fields.Date.today()
                    serial.serial_id.write(vals)
                    serial_id = serial.serial_id.id
                else:
                    if serial.state == 'approved':
                        vals = {
                            'lot_id': mrp.lot_producing_id.id,
                            'name': serial.name,
                        }
                        if not serial.serial_id or not serial.serial_id.date:
                            vals['date'] = fields.Date.today()
                        serial_id = sl_obj.create(vals).id
                        serial.serial_id = serial_id

                if serial_id:
                    sl_vals = {
                        'location_id': mrp.product_id.with_company(self.company_id).property_stock_production.id,
                        'location_dest_id': mrp.location_dest_id.id,
                        'date': fields.Datetime.now(),
                        'quantity': serial.quantity,
                        'serial_id': serial_id
                    }
                    if serial.serial_line_id:
                        serial.serial_line_id.write(sl_vals)
                    else:
                        serial_line_id = ssl.create(sl_vals).id
                        serial.serial_line_id = serial_line_id

                    sn = sl_obj.browse(serial_id)
                    sn.action_create_sl()
            self._cr.commit()
            mrp.lot_producing_id.action_create_sl()
        return True
    
    def action_qc_entries(self):
        picking_obj = self.env['stock.picking']
        for mrp in self:
            if mrp.qc_id and mrp.product_id.categ_id.category_type != 'fg' and not mrp.rejection_picking_id:
                    picking_type = mrp.company_id.factory_wipreject_id
                    qty = round((mrp.qty_producing/mrp.batch_qty)*mrp.qc_id.reject_qty, 3)
                    new_picking = picking_obj.create({
                        'picking_type_id': picking_type.id,
                        'location_id': picking_type.default_location_src_id.id, 
                        'location_dest_id': picking_type.default_location_dest_id.id,
                        'origin': mrp.name,
                        'immediate_transfer': False,
                        'company_id': self.env.user.company_id.id
                        })
                    mrp.rejection_picking_id = new_picking.id
                    new_move = self.env['stock.move'].create({
                        'location_id': picking_type.default_location_src_id.id, 
                        'location_dest_id': picking_type.default_location_dest_id.id,
                        'picking_id': new_picking.id,
                        'product_id': mrp.product_id.id,
                        'name': mrp.product_id.name_get()[0][1],
                        'product_uom_qty': qty,
                        'product_uom': mrp.product_id.uom_id.id
                        })
                    self.env['stock.move.line'].create({
                        'location_id': picking_type.default_location_src_id.id, 
                        'location_dest_id': picking_type.default_location_dest_id.id,
                        'picking_id': new_picking.id,
                        'product_id': mrp.product_id.id,
                        'move_id': new_move.id,
                        'qty_done': qty,
                        'lot_id': mrp.lot_producing_id.id
                        })
                    new_picking.action_confirm()
                    new_picking.action_assign()
                    new_picking.button_validate()
        return True
    
    def button_mark_done(self):
        for mrp in self:
            for move in mrp.move_raw_ids:
                if move.bom_qty <= 0:
                    continue
                line_qty = 0.0
                if move.bom_qty > 0:
                    for move_line in move.move_line_ids:
                        move_line.qty_done = round(move_line.reserved_uom_qty, 3)
                        line_qty += round(move_line.qty_done, 3)
                    move.quantity_done = line_qty
                    bom_qty = round(move.bom_qty * mrp.batch_qty, 3)
                    if round(move.quantity_done, 3) != round(bom_qty, 3):
                        raise UserError('Done Qty not matching with Bom Qty * Batch Qty for %s'%(move.product_id.name_get()[0][1]))
            if mrp.product_id.categ_id.category_type == 'sfg' and not mrp.product_id.master_batch:
                mrp.create_auto_lot()
            if mrp.product_id.product_group3_id and mrp.product_id.product_group3_id.skip_quality:
                pass
            else:
                if mrp.picking_type_id.quality_check:
                    if not mrp.qc_id:
                        raise UserError('Cannot process MO without Quality Check!')
                    if mrp.qc_id:
                        if not mrp.qc_id.line_ids:
                            raise UserError('Please create MO Parameters for Category %s!'%(self.product_id.categ_id.name))
                        if mrp.qc_id.state != 'completed':
                            raise UserError('Cannot process MO without completing Quality Check!')
            if mrp.product_id.master_batch:
                if not mrp.product_id.lot_sequence_id:
                    raise UserError("Enter Lot Sequence for %s"%(mrp.product_id.name))
                if not mrp.lot_producing_id:
                    self.lot_producing_id = self.env['stock.lot'].create({
                        'product_id': mrp.product_id.id,
                        'company_id': mrp.company_id.id,
                        'name': mrp.product_id.lot_sequence_id.next_by_id()
                        })
            if mrp.product_id.categ_id.category_type == 'fg':
                sn_count = len([line.id for line in mrp.serial_line_ids if line.state == 'approved'])
                if mrp.batch_qty != sn_count:
                    raise UserError("Batch Qty should match with Approved Serial Numbers")
                mrp.create_auto_lot()
            if mrp.qty_producing <= 0:
                mrp.qty_producing = mrp.product_qty
            if mrp.picking_type_id.quality_check:
                mrp.action_qc_entries()
            if mrp.product_id.conversion_cost:
                mrp.conversion_cost = mrp.product_id.conversion_cost
            for move in mrp.move_raw_ids:
                if move.state != 'done':
                    move._action_done()
            mrp.state = 'done'
            if mrp.product_id.categ_id.category_type == 'fg':
                mrp.create_serial_numbers()
            if mrp.move_finished_ids:
                for move in mrp.move_finished_ids:
                    if not move.move_line_ids:
                        self.env['stock.move.line'].create({
                            'location_id': 15, 
                            'location_dest_id': mrp.location_dest_id.id,
                            'product_id': mrp.product_id.id,
                            'qty_done': mrp.qty_producing,
                            'lot_id': mrp.lot_producing_id.id,
                            'branch_id': 2,
                            'move_id': move.id,
                            'lot_id': mrp.lot_producing_id.id,
                            })
                    move._action_done()
            if not mrp.move_finished_ids:
                move_lines = [(0, 0, {
                    'location_id': 15, 
                    'location_dest_id': mrp.location_dest_id.id,
                    'product_id': mrp.product_id.id,
                    'qty_done': mrp.product_qty,
                    'lot_id': mrp.lot_producing_id.id,
                    'branch_id': 2,
                    })]
                new_move = self.env['stock.move'].create({
                    'location_id': 15, 
                    'location_dest_id': mrp.location_dest_id.id,
                    'product_id': mrp.product_id.id,
                    'name': mrp.product_id.name_get()[0][1],
                    'product_uom_qty': mrp.product_qty,
                    'quantity_done': mrp.product_qty,
                    'product_uom': mrp.product_id.uom_id.id,
                    'branch_id': 2,
                    'production_id': mrp.id,
                    'move_line_ids': move_lines
                    })
                new_move._action_done()
            mrp.mrp_svl_correction()
        return True
    
    def mrp_svl_correction(self):
        svl_obj = self.env['stock.valuation.layer']
        branch_id = 2
        for mrp in self:
            total_cost = 0.0
            for move in mrp.move_raw_ids:
                date = move.date
                move_cost = 0.0
                if move.state != 'done':
                    continue
                move.manual_consumed_ok = False
                if move.move_line_ids:
                    for move_line in move.move_line_ids:
                        unit_cost = 0.0
                        domain = [
                            ('product_id', '=', move.product_id.id),
                            ('quantity', '>', 0),
                            ('branch_id', '=', branch_id),
                            ('create_date', '<', date)
                            ]
                        if move_line.lot_id:
                            domain.append(('lot_id', '=', move_line.lot_id.id))
                        svl_ins = svl_obj.search(domain, order='create_date desc')
                        if svl_ins:
                            unit_cost = svl_ins[0].unit_cost
                        else:
                            domain = [
                                ('product_id', '=', move.product_id.id),
                                ('quantity', '>', 0),
                                ('branch_id', '=', branch_id),
                                ('create_date', '<', date)
                                ]
                            svl_ins = svl_obj.search(domain, order='create_date desc')
                            if svl_ins:
                                unit_cost = svl_ins[0].unit_cost
                        if unit_cost > 0:
                            qty = round(move_line.qty_done, 3)
                            value = round(qty * round(unit_cost, 3), 2)
                            total_cost += value
                            move_cost += value
                            move_line.unit_cost = unit_cost
                if move.stock_valuation_layer_ids:
                    for svl in move.stock_valuation_layer_ids:
                        svl.correct_svl_jv()
                        svl.correct_to_smldate()
                else:
                    svl_list = move._create_out_svl()
                    for svl in svl_list:
                        svl.correct_svl_jv()
                        svl.correct_to_smldate()
                move.price_unit = move_cost
            if not mrp.move_finished_ids:
                unit_cost = round(round(total_cost / mrp.product_qty, 3) + mrp.product_id.conversion_cost, 3)
                move_lines = [(0, 0, {
                    'location_id': 15, 
                    'location_dest_id': mrp.location_dest_id.id,
                    'product_id': mrp.product_id.id,
                    'qty_done': mrp.product_qty,
                    'lot_id': mrp.lot_producing_id.id,
                    'branch_id': 2,
                    'unit_cost': unit_cost,
                    })]
                new_move = self.env['stock.move'].create({
                    'location_id': 15, 
                    'location_dest_id': mrp.location_dest_id.id,
                    'product_id': mrp.product_id.id,
                    'name': mrp.product_id.name_get()[0][1],
                    'product_uom_qty': mrp.product_qty,
                    'quantity_done': mrp.product_qty,
                    'product_uom': mrp.product_id.uom_id.id,
                    'branch_id': 2,
                    'price_unit': unit_cost,
                    'production_id': mrp.id,
                    'move_line_ids': move_lines
                    })
                new_move._action_done()
            for move in mrp.move_finished_ids:
                move.product_uom_qty = mrp.qty_producing
                move.quantity_done = mrp.qty_producing
                unit_cost = round(round(total_cost / move.quantity_done, 3) + mrp.product_id.conversion_cost, 3)
                qty = round(move.quantity_done, 3)
                total_cost = round(unit_cost * qty, 2)
                if move.state == 'done':
                    move_line = move.move_line_ids[0]
                    move_line.unit_cost = unit_cost
                    for svl in move.stock_valuation_layer_ids:
                        svl.correct_svl_jv()
                        svl.correct_to_smldate()
                else:
                    if not move.move_line_ids:
                        move_line = self.env['stock.move.line'].create({
                            'location_id': 15, 
                            'location_dest_id': mrp.location_dest_id.id,
                            'product_id': mrp.product_id.id,
                            'qty_done': mrp.qty_producing,
                            'lot_id': mrp.lot_producing_id.id,
                            'branch_id': 2,
                            'unit_cost': unit_cost,
                            'state': 'done',
                            'date': date,
                            'move_id': move.id
                            })
                    for move_line in move.move_line_ids:
                        move_line.write({
                            'date': date, 
                            'state': 'done', 
                            'unit_cost': unit_cost, 
                            'lot_id': mrp.lot_producing_id.id,
                            'qty_done': mrp.qty_producing
                            })
                    move.write({'state': 'done', 'date': date})
                if move.stock_valuation_layer_ids:
                    for svl in move.stock_valuation_layer_ids:
                        svl.lot_id = mrp.lot_producing_id.id
                        svl.quantity = mrp.qty_producing
                        svl.correct_svl_jv()
                        svl.correct_to_smldate()
                else:
                    svl_list = move._create_in_svl()
                    for svl in svl_list:
                        svl.lot_id = mrp.lot_producing_id.id
                        svl.correct_svl_jv()
                        svl.correct_to_smldate()
            count = 0
            for move in mrp.move_finished_ids:
                count += 1
                if count != 1:
                    for svl in move.stock_valuation_layer_ids:
                        svl.delete_svl_sm_am()
        return True
    
    def action_confirm(self):
        for mrp in self:
            move_bom_dic = {}
            for move in mrp.move_raw_ids:
                if move.bom_qty:
                    move_bom_dic.update({move.id: move.bom_qty})
                elif move.bom_line_id:
                    move_bom_dic.update({move.id: move.bom_line_id.product_qty})
        res = super(Production, self).action_confirm()
        for mrp in self:
            if mrp.product_id.curing_ok:
                for shift in ['shift1', 'shift2', 'shift3']:
                    self.env['mrp.shift.line'].create({
                        'production_id': mrp.id,
                        'shift': shift
                        })
            for mrp in self:
                for move in mrp.move_raw_ids:
                    if move.id in move_bom_dic:
                        move.bom_qty = move_bom_dic[move.id]
        return res
    
    def action_assign(self):
        for mrp in self:
            mrp.move_raw_ids.with_context(mrp_assign=True)._action_assign()
        for mrp in self:
            move_bom_dic = {}
            for move in mrp.move_raw_ids:
                if move.bom_qty:
                    move_bom_dic.update({move.id: move.bom_qty})
                elif move.bom_line_id:
                    move_bom_dic.update({move.id: move.bom_line_id.product_qty})
        res = super(Production, self).action_assign()
        for mrp in self:
            for move in mrp.move_raw_ids:
                if move.id in move_bom_dic:
                    move.bom_qty = move_bom_dic[move.id]
        return res
        
    def _get_move_raw_values(self, product_id, product_uom_qty, product_uom, operation_id=False, bom_line=False):
        source_location = self.location_src_id
        data = {
            'sequence': bom_line.sequence if bom_line else 10,
            'name': _('New'),
            'date': self.date_planned_start,
            'date_deadline': self.date_planned_start,
            'bom_line_id': bom_line.id if bom_line else False,
            'picking_type_id': self.picking_type_id.id,
            'product_id': product_id.id,
            'product_uom_qty': product_uom_qty,
            'product_uom': product_uom.id,
            'location_id': source_location.id,
            'location_dest_id': self.product_id.with_company(self.company_id).property_stock_production.id,
            'raw_material_production_id': self.id,
            'company_id': self.company_id.id,
            'operation_id': operation_id,
            'price_unit': product_id.standard_price,
            'procure_method': 'make_to_stock',
            'origin': self._get_origin(),
            'state': 'draft',
            'warehouse_id': source_location.warehouse_id.id,
            'group_id': self.procurement_group_id.id,
            'propagate_cancel': self.propagate_cancel,
            'manual_consumption': self.env['stock.move']._determine_is_manual_consumption(product_id, self, bom_line),
            'bom_qty': bom_line.product_qty,
            'actual_bom_qty': bom_line.product_qty if bom_line else False
            }
        return data
    
    # def action_assign(self):
    #     for production in self:
    #         production.move_raw_ids.with_context(mrp_assign=True)._action_assign()
    #     return True
    
    def _post_inventory(self, cancel_backorder=False):
        moves_to_do, moves_not_to_do = set(), set()
        for move in self.move_raw_ids:
            if move.state == 'done':
                moves_not_to_do.add(move.id)
            elif move.state != 'cancel':
                moves_to_do.add(move.id)
                if move.product_qty == 0.0 and move.quantity_done > 0:
                    move.product_uom_qty = move.quantity_done
        self.env['stock.move'].browse(moves_to_do)._action_done(cancel_backorder=cancel_backorder)
        moves_to_do = self.move_raw_ids.filtered(lambda x: x.state == 'done') - self.env['stock.move'].browse(moves_not_to_do)
        # Create a dict to avoid calling filtered inside for loops.
        moves_to_do_by_order = defaultdict(lambda: self.env['stock.move'], [
            (key, self.env['stock.move'].concat(*values))
            for key, values in tools_groupby(moves_to_do, key=lambda m: m.raw_material_production_id.id)
        ])
        for order in self:
            finish_moves = order.move_finished_ids.filtered(lambda m: m.product_id == order.product_id and m.state not in ('done', 'cancel'))
            # the finish move can already be completed by the workorder.
            if finish_moves and not finish_moves.quantity_done:
                finish_moves._set_quantity_done(float_round(order.qty_producing - order.qty_produced, precision_rounding=order.product_uom_id.rounding, rounding_method='HALF-UP'))
                finish_moves.move_line_ids.lot_id = order.lot_producing_id
            # workorder duration need to be set to calculate the price of the product
            for workorder in order.workorder_ids:
                if workorder.state not in ('done', 'cancel'):
                    workorder.duration_expected = workorder._get_duration_expected()
                if workorder.duration == 0.0:
                    workorder.duration = workorder.duration_expected * order.qty_produced/order.product_qty
            order._cal_price(moves_to_do_by_order[order.id])
        moves_to_finish = self.move_finished_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
        moves_to_finish = moves_to_finish._action_done(cancel_backorder=cancel_backorder)
        self.move_raw_ids.with_context(normal_assign=True)._action_assign()
        for order in self:
            consume_move_lines = moves_to_do_by_order[order.id].mapped('move_line_ids')
            order.move_finished_ids.move_line_ids.consume_line_ids = [(6, 0, consume_move_lines.ids)]
        return True
    
class MrpScraps(models.Model):
    _name = 'mrp.scrap'
    _description = 'MRP Scraps'
    
    @api.depends('line_ids', 'line_ids.weight')
    def _total_weight(self):
        for scrap in self:
            scrap.total_weight = sum([line.weight for line in scrap.line_ids])
        
    date = fields.Date('Date', default=lambda self: fields.Date.today(), required=True)
    name = fields.Char('Reference No.', default='/')
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')],'Status', default='draft')
    line_ids = fields.One2many('mrp.scrap.line', 'scrap_id', 'Lines')
    total_weight = fields.Float('Total Weight', compute='_total_weight', store=True)

class MrpShiftLines(models.Model):
    _name = 'mrp.shift.line'
    _description = 'Press Shift Lines'
    
    shift = fields.Selection([('shift1', 'Shift 1'), ('shift2', 'Shift 2'), ('shift3', 'Shift 3')], 'Shift', required=True)
    press_1 = fields.Float('Press 1')
    press_2 = fields.Float('Press 2')
    press_3 = fields.Float('Press 3')
    press_4 = fields.Float('Press 4')
    press_5 = fields.Float('Press 5')
    press_6 = fields.Float('Press 6')
    press_7 = fields.Float('Press 7')
    production_id = fields.Many2one('mrp.production', 'MO')

class ShiftLines(models.Model):
    _name = 'shift.line'
    _description = 'Shift Lines'
    
    date = fields.Date('Date', required=True)
    shift_1 = fields.Float('Shift 1')
    shift_2 = fields.Float('Shift 2')
    shift_3 = fields.Float('Shift 3')
    production_id = fields.Many2one('mrp.production', 'MO')
    
class PressShiftLines(models.Model):
    _name = 'press.shift.line'
    _description = 'Press Shift Lines'
    
    shift = fields.Selection([('shift1', 'Shift 1'), ('shift2', 'Shift 2'), ('shift3', 'Shift 3')], 'Shift', required=True)
    press_1 = fields.Float('Press 1')
    press_2 = fields.Float('Press 2')
    press_3 = fields.Float('Press 3')
    press_4 = fields.Float('Press 4')
    press_5 = fields.Float('Press 5')
    press_6 = fields.Float('Press 6')
    press_7 = fields.Float('Press 7')
    production_id = fields.Many2one('mrp.production', 'MO')
    
class MrpScrapLines(models.Model):
    _name = 'mrp.scrap.line'
    _description = 'MRP Scrap Lines'
    
    @api.depends('scrap_id', 'scrap_id.date', 'scrap_id.name', 'scrap_id.state')
    def _compute_details(self):
        for line in self:
            line.date = line.scrap_id.date
            line.state = line.scrap_id.state
            
    date = fields.Date('Date', compute='_compute_details', store=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')],'Status', compute='_compute_details', store=True)
    press = fields.Selection([
        ('press1', 'Press1'), ('press2', 'Press2'), ('press3', 'Press3'),
        ('press4', 'Press4'), ('press5', 'Press5'), ('press6', 'Press6'),
        ('press7', 'Press7')], 'Press', required=True)
    shift = fields.Selection([('shift1', 'Shift1'), ('shift2', 'Shift2'), ('shift3', 'Shift3')], 'Shift', required=True)
    weight = fields.Float('Weight', required=True)
    scrap_id = fields.Many2one('mrp.scrap', 'Reference')
    
class StockMoves(models.Model):
    _inherit = 'stock.move'
    
    def action_status_done(self):
        for move in self:
            move.state = 'done'
        return True
    
    def action_status_cancel(self):
        for move in self:
            move.state = 'cancel'
        return True
    
    def write(self, vals):
        if 'bom_qty' in vals:
            if self.raw_material_production_id:
                msg = '%s'%(self.product_id.name)
                ref_fields = self.env['stock.move'].fields_get(['bom_qty'])
                tracking_value_ids = self._mail_track(ref_fields, {'bom_qty': vals['bom_qty']})[1]
                self.raw_material_production_id._message_log(body=msg, tracking_value_ids=tracking_value_ids)
        return super(StockMoves, self).write(vals)
    
    def action_open_product_lot(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_production_lot_form")
        action['domain'] = [('product_id.product_tmpl_id', '=', self.product_id.product_tmpl_id.id)]
        action['context'] = {
            'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
            }
        return action
    
    def _get_bom_line_qty(self):
        for line in self:
            if line.bom_line_id:
                line.bom_qty = line.bom_line_id.product_qty
            else:
                line.bom_qty = 0
    
    def _compute_current_stock(self):
        for line in self:
            if line.product_id and line.location_id:
                line.current_stock = line._get_available_quantity(line.location_id) + line.reserved_availability
            else:
                line.current_stock = 0
    
    def _compute_consumed_qty(self):
        for line in self:
            if line.manual_consumed_ok:
                line.mrp_consumed_qty = line.mrp_manual_consumed_qty
            else:
                line.mrp_consumed_qty = round(sum([line.qty_done for line in line.move_line_ids]), 3)
                
    bom_qty = fields.Float('BoM Qty', digits=(16,3))
    actual_bom_qty = fields.Float('Actual BoM Qty', digits=(16,3), readonly=False)
    current_stock = fields.Float('WIP Available Stock', compute='_compute_current_stock', digits=(16,3))
    mrp_manual_consumed_qty = fields.Float('MRP Consumed Qty(Manual)', digits=(16,3))
    mrp_consumed_qty = fields.Float('Consumed Qty', compute='_compute_consumed_qty', digits=(16,3))
    manual_consumed_ok = fields.Boolean('Manual Qty')
    
    @api.onchange('bom_qty')
    def onchange_bom_qty(self):
        if self.bom_qty:
            self.product_uom_qty = round(self.raw_material_production_id.batch_qty * self.bom_qty, 3)

class MrpStockReport(models.TransientModel):
    _inherit = 'stock.traceability.report'
    
    def _make_dict_move(self, level, parent_id, move_line, unfoldable=False):
        res_model, res_id, ref = self._get_reference(move_line)
        dummy, is_used = self._get_linked_move_lines(move_line)
        data = [{
            'level': level,
            'unfoldable': unfoldable,
            'date': move_line.move_id.date,
            'parent_id': parent_id,
            'is_used': bool(is_used),
            'usage': self._get_usage(move_line),
            'model_id': move_line.id,
            'model': 'stock.move.line',
            'product_id': move_line.product_id.display_name,
            'product_qty_uom': "%s %s" % (self._quantity_to_str(move_line.product_uom_id, move_line.product_id.uom_id, move_line.qty_done), move_line.product_id.uom_id.name),
            'bom_qty': move_line.move_id.raw_material_production_id and move_line.move_id.bom_qty and str(move_line.move_id.bom_qty) or '',
            'lot_name': move_line.lot_id.name,
            'lot_id': move_line.lot_id.id,
            'location_source': move_line.location_id.usage == 'internal' and move_line.location_id.complete_name or move_line.location_id.name,
            'location_destination': move_line.location_dest_id.usage == 'internal' and move_line.location_dest_id.complete_name or move_line.location_dest_id.name,
            'reference_id': ref,
            'res_id': res_id,
            'res_model': res_model}]
        return data
    
    @api.model
    def _final_vals_to_lines(self, final_vals, level):
        lines = []
        for data in final_vals:
            lines.append({
                'id': autoIncrement(),
                'model': data['model'],
                'model_id': data['model_id'],
                'parent_id': data['parent_id'],
                'usage': data.get('usage', False),
                'is_used': data.get('is_used', False),
                'lot_name': data.get('lot_name', False),
                'lot_id': data.get('lot_id', False),
                'reference': data.get('reference_id', False),
                'res_id': data.get('res_id', False),
                'res_model': data.get('res_model', False),
                'columns': [data.get('reference_id', False),
                            data.get('product_id', False),
                            format_datetime(self.env, data.get('date', False), tz=False, dt_format=False),
                            data.get('lot_name', False),
                            data.get('location_source', False),
                            data.get('location_destination', False),
                            data.get('bom_qty', 0),
                            data.get('product_qty_uom', 0)],
                'level': level,
                'unfoldable': data['unfoldable'],
            })
        return lines

class MrpCostStructure(models.AbstractModel):
    _inherit = 'report.mrp_account_enterprise.mrp_cost_structure'
    _description = 'MRP Cost Structure Report'

    def get_lines(self, productions):
        ProductProduct = self.env['product.product']
        StockMove = self.env['stock.move']
        res = []
        # currency_table = self.env['res.currency']._get_query_currency_table({'multi_company': True, 'date': {'date_to': fields.Date.today()}})
        for product in productions.mapped('product_id'):
            mos = productions.filtered(lambda m: m.product_id == product)
            total_cost_by_mo = defaultdict(float)
            component_cost_by_mo = defaultdict(float)
            operation_cost_by_mo = defaultdict(float)

            operations = []
            total_cost_operations = 0.0

            raw_material_moves = {}
            total_cost_components = 0.0
            sm_ids = self.env['stock.move'].search([
                ('raw_material_production_id', 'in', mos.ids)
                ]).ids
            svls = self.env['stock.valuation.layer'].search([
                ('stock_move_id', 'in', sm_ids)
                ])
            for svl in svls:
                product_id = svl.product_id.id
                mo_id = svl.stock_move_id.raw_material_production_id.id
                cost = round(abs(svl.value), 3)
                qty = round(abs(svl.quantity), 3)
                if product_id in raw_material_moves:
                    product_moves = raw_material_moves[product_id]
                    total_cost = product_moves['cost'] + cost
                    total_qty = product_moves['qty'] + qty
                    unit_cost = round(total_cost / total_qty, 3)
                    product_moves['unit_cost'] = unit_cost
                    product_moves['cost'] = total_cost
                    product_moves['qty'] = total_qty
                else:
                    raw_material_moves[product_id] = {
                        'qty': qty,
                        'cost': cost,
                        'unit_cost': round(svl.unit_cost, 3),
                        'product_id': ProductProduct.browse(product_id),
                        }
                total_cost_by_mo[mo_id] += cost
                component_cost_by_mo[mo_id] += cost
                total_cost_components += cost
            raw_material_moves = list(raw_material_moves.values())
            # Get the cost of scrapped materials
            scraps = StockMove.search([
                ('production_id', 'in', mos.ids), 
                ('scrapped', '=', True), 
                ('state', '=', 'done')])

            # Get the byproducts and their total + avg per uom cost share amounts
            total_cost_by_product = defaultdict(float)
            qty_by_byproduct = defaultdict(float)
            qty_by_byproduct_w_costshare = defaultdict(float)
            component_cost_by_product = defaultdict(float)
            operation_cost_by_product = defaultdict(float)
            # tracking consistent uom usage across each byproduct when not using byproduct's product uom is too much of a pain
            # => calculate byproduct qtys/cost in same uom + cost shares (they are MO dependent)
            byproduct_moves = mos.move_byproduct_ids.filtered(lambda m: m.state != 'cancel')
            for move in byproduct_moves:
                qty_by_byproduct[move.product_id] += move.product_qty
                # byproducts w/o cost share shouldn't be included in cost breakdown
                if move.cost_share != 0:
                    qty_by_byproduct_w_costshare[move.product_id] += move.product_qty
                    cost_share = move.cost_share / 100
                    total_cost_by_product[move.product_id] += total_cost_by_mo[move.production_id.id] * cost_share
                    component_cost_by_product[move.product_id] += component_cost_by_mo[move.production_id.id] * cost_share
                    operation_cost_by_product[move.product_id] += operation_cost_by_mo[move.production_id.id] * cost_share

            # Get product qty and its relative total + avg per uom cost share amount
            uom = product.uom_id
            mo_qty = 0
            for m in mos:
                # cost_share = float_round(1 - sum(m.move_finished_ids.mapped('cost_share')) / 100, precision_rounding=0.0001)
                # total_cost_by_product[product] += total_cost_by_mo[m.id] * cost_share
                # component_cost_by_product[product] += component_cost_by_mo[m.id] * cost_share
                # operation_cost_by_product[product] += operation_cost_by_mo[m.id] * cost_share
                qty = sum(m.move_finished_ids.filtered(lambda mo: mo.state == 'done' and mo.product_id == product).mapped('product_uom_qty'))
                if m.product_uom_id.id == uom.id:
                    mo_qty += qty
                else:
                    mo_qty += m.product_uom_id._compute_quantity(qty, uom)
                # conversion_cost = round(m.conversion_cost * m.product_qty, 3)
            mo = mos[0]
            mo_qty = mo.move_finished_ids and mo.move_finished_ids[0].quantity_done or 0.0
            unit_cost_components = round(total_cost_components/mo_qty, 3)
            conversion_cost = round(m.conversion_cost, 3)
            unit_cost = round(m.unit_cost, 3)
            total_cost = round(unit_cost * mo_qty, 2)
            res.append({
                'product': product,
                'mo_qty': mo_qty,
                'mo_uom': uom,
                'operations': operations,
                'currency': self.env.company.currency_id,
                'raw_material_moves': raw_material_moves,
                'total_cost_components': total_cost_components,
                'unit_cost_components': unit_cost_components,
                'total_cost_operations': total_cost_operations,
                'total_cost': total_cost,
                'scraps': scraps,
                'mocount': len(mos),
                'byproduct_moves': byproduct_moves,
                'component_cost_by_product': component_cost_by_product,
                'operation_cost_by_product': operation_cost_by_product,
                'qty_by_byproduct': qty_by_byproduct,
                'qty_by_byproduct_w_costshare': qty_by_byproduct_w_costshare,
                'total_cost_by_product': total_cost_by_product,
                'conversion_cost': conversion_cost,
                'unit_cost': unit_cost
            })
        return res
    