# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def _create_returns(self):
        new_picking_id, pick_type_id = super(StockReturnPicking, self)._create_returns()
        new_picking = self.env['stock.picking'].browse([new_picking_id])
        for serial in self.picking_id.serial_line_ids:
            self.env['picking.serial.line'].create({
                'serial_id': serial.serial_id.id,
                'lot_id': serial.lot_id.id,
                'picking_id': new_picking.id,
                'product_id': serial.product_id.id,
                'alt_uom_id': serial.alt_uom_id.id,
                'quantity': serial.quantity
                })
        return new_picking_id, pick_type_id
    
    def _prepare_move_default_values(self, return_line, new_picking):
        vals = super(StockReturnPicking, self)._prepare_move_default_values(return_line, new_picking)
        vals.update({'price_unit': return_line.move_id.price_unit})
        return vals