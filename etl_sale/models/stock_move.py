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

class StockMoves(models.Model):
    _inherit = 'stock.move'
    
    def _compute_done_qty(self):
        for move in self:
            psl_obj = self.env['picking.serial.line']
            done_qty = 0
            if move.picking_id and move.alt_uom_id and move.picking_id.serial_line_ids:
                psls = psl_obj.search([
                    ('product_id', '=', move.product_id.id),
                    ('alt_uom_id', '=', move.alt_uom_id.id),
                    ('scanned', '=', True),
                    ('picking_id', '=', move.picking_id.id)
                    ])
                if move.alt_uom_id.type == 'base':
                    done_qty = psls and len(psls.ids) or 0
                else:
                    for psl in psls:
                        done_qty += round((psl.quantity / move.product_id.weight_belt), 0)
                    
            move.alt_uom_qty_actual = done_qty
            
    alt_uom_id = fields.Many2one('product.alt.uom', 'Package Name')
    alt_uom_qty = fields.Integer('Demand Qty')
    alt_uom_qty_actual = fields.Integer('Done Qty', compute='_compute_done_qty')
    alt_uom_qty_reserved = fields.Integer('Reserved Qty')
    recompute = fields.Boolean()
    