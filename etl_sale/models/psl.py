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
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from cgitb import reset
from odoo.tools import float_is_zero, float_compare, float_round
import logging
logger = logging.getLogger(__name__)

class StockSerialLine(models.Model):
    _name = 'picking.serial.line'
    _description = 'Picking Serial Numbers'
    
    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        res = super(StockSerialLine, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
        return res
    
    @api.depends('serial_id', 'serial_id.name')
    def _compute_product(self):
        for line in self:
            if line.serial_id and line.serial_id.product_id:
                line.product_id = line.serial_id.product_id.id
                line.lot_id = line.serial_id.lot_id.id
                line.name = line.serial_id.name
            else:
                line.product_id = False
                line.lot_id = False
                line.name = ''
    
    @api.onchange('serial_id')
    def onchange_serial(self):
        if self.serial_id:
            if self.serial_id.get_location_qty(self.picking_id.location_id.id) == 0:
                raise UserError('Cannot select serial number with Zero Qty.')
            self.reserved = True
            self.quantity = self.serial_id.get_location_qty(self.picking_id.location_id.id)
        self.scanned = False
                
    serial_id = fields.Many2one('stock.serial', 'Serial Number', required=True)
    move_id = fields.Many2one('stock.move', 'Move')
    product_id = fields.Many2one('product.product', 'Product', compute='_compute_product', store=True)
    name = fields.Char('SN', compute='_compute_product', store=True)
    quantity = fields.Float('Weight', digits=(16,3))
    lot_id = fields.Many2one('stock.lot', 'Lot', compute='_compute_product', store=True)
    picking_id = fields.Many2one('stock.picking', 'Picking')
    serial_line_out_id = fields.Many2one('stock.serial.line')
    reserved = fields.Boolean('Reserved')
    alt_uom_id = fields.Many2one('product.alt.uom', 'Package Name')
    branch_transit_created = fields.Boolean('Branch Transit Created')
    scanned = fields.Boolean('Scanned')
    
    def create_move(self):
        sm_obj = self.env['stock.move']
        psls = self.search([
            ('product_id', '=', self.product_id.id),
            ('picking_id', '=', self.picking_id.id),
            ('alt_uom_id', '=', self.alt_uom_id.id)
            ])
        total_qty = sum([psl.quantity for psl in psls])
        new_move = sm_obj.create({
            'product_id': self.product_id.id,
            'alt_uom_qty': len(psls.ids),
            'alt_uom_qty_actual': len(psls.ids),
            'product_uom_qty': total_qty,
            'quantity_done': total_qty,
            'location_id': self.picking_id.location_id.id,
            'location_dest_id': self.picking_id.location_dest_id.id,
            'picking_type_id': self.picking_id.picking_type_id.id,
            'name': self.product_id.name
            })
        sml_obj = self.env['stock.move.line']
        lot_dic = {}
        for psl in psls:
            if psl.lot_id.id in lot_dic:
                lot_dic.update({psl.lot_id: lot_dic[psl.lot_id.id] + psl.quantity})
            else:
                lot_dic.update({psl.lot_id: psl.quantity})
        for lot in lot_dic:
            sml_vals = {
                'move_id': new_move.id,
                'product_id': self.product_id.id,
                'lot_id': lot.id,
                'reserved_uom_qty': lot_dic[lot],
                'qty_done': lot_dic[lot],
                'location_id': self.picking_id.location_id.id,
                'location_dest_id': self.picking_id.location_dest_id.id,
                'picking_id': self.picking_id.id,
                'branch_id': self.picking_id.branch_id.id
                }
            sml_obj.create(sml_vals)
                        
        return True