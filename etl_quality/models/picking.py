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
    
class Picking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        for picking in self:
            if picking.picking_type_id.quality_check:
                if picking.picking_type_id.code == 'incoming' and not picking.partner_id.is_branch:
                    qc_reqd_count, qc_done_count = 0, 0
                    for move in self.move_ids_without_package:
                        if move.product_id.qc_ok:
                            if move.qc_id:
                                qc_reqd_count += 1
                                if move.qc_id.state != 'completed':
                                    raise UserError('Cannot process GRN without completing Quality Check!')
                                if move.qc_id.state == 'completed':
                                    qc_done_count += 1
                                if round(move.quantity_done, 2) != round(move.qc_id.accept_qty+move.qc_id.reject_qty, 2):
                                    raise UserError('Done Quantity should be same as QC Qty!')
                                if move.quantity_done > 0 and not move.qc_id:
                                    raise UserError('Cannot process GRN without completing Quality Check!')
                    if qc_reqd_count > 0:
                        if qc_done_count < 1:
                            raise UserError('Cannot process GRN without completing Quality Check!')
        res =  super(Picking, self).button_validate()
        for picking in self:
            new_picking_id = False
            if picking.picking_type_id.code == 'incoming' and picking.state == 'done':
                for move in self.move_ids_without_package:
                    if move.qc_id and move.qc_id.reject_qty > 0:
                        picking_type = self.company_id.factory_qcreject_id
                        qty = move.qc_id.reject_qty
                        # if not new_picking_id:
                        #     new_picking = self.env['stock.picking'].create({
                        #         'picking_type_id': picking_type.id,
                        #         'location_id': picking_type.default_location_src_id.id, 
                        #         'location_dest_id': picking_type.default_location_dest_id.id,
                        #         'origin': self.name,
                        #         'immediate_transfer': False,
                        #         'company_id': self.env.user.company_id.id
                        #         })
                        #     new_picking_id = True
                        # self.rejection_picking_id = new_picking.id
                        new_move = self.env['stock.move'].create({
                            'location_id': picking_type.default_location_src_id.id, 
                            'location_dest_id': picking_type.default_location_dest_id.id,
                            # 'picking_id': new_picking.id,
                            'product_id': self.product_id.id,
                            'name': self.product_id.name_get()[0][1],
                            'product_uom_qty': qty,
                            'product_uom': self.product_id.uom_id.id
                            })
                        self.env['stock.move.line'].create({
                            'location_id': picking_type.default_location_src_id.id, 
                            'location_dest_id': picking_type.default_location_dest_id.id,
                            # 'picking_id': new_picking.id,
                            'product_id': self.product_id.id,
                            'move_id': new_move.id,
                            'qty_done': qty,
                            'lot_id': move.move_line_ids[0].lot_id.id
                            })
                        new_move._action_done()
                # if new_picking_id:
                #     new_picking.action_confirm()
                #     new_picking.action_assign()
                #     new_picking.with_context(no_qty_check=True).button_validate()
        return res

    def _compute_grn(self):
        for picking in self:
            if picking.picking_type_id and picking.picking_type_id.code == 'incoming':
                picking.grn = True
            else:
                picking.grn = False

    grn = fields.Boolean('GRN', compute='_compute_grn')
    qc_ids = fields.One2many('grn.qc', 'picking_id', 'GRN QC')
    rejection_picking_id = fields.Many2one('stock.picking', 'GRN Rejection IM')

class StockMove(models.Model):
    _inherit = 'stock.move'
    
    def action_qc(self):
        if not self.qc_id:
            params = self.env['grn.parameter'].search([('product_id', '=', self.product_id.id)])
            if not params:
                raise UserError('Please create GRN QC Parameters for %s!'%(self.product_id.name))
            for param in params:
                if not param.line_ids:
                    raise UserError('Please create GRN QC Parameters for %s!'%(self.product_id.name))
            qc_id = self.env['grn.qc'].create({
                'picking_id': self.picking_id.id,
                'product_id': self.product_id.id,
                'grn_qty': self.product_uom_qty
                }).id
            self.qc_id = qc_id
            params = self.env['grn.parameter'].search([('product_id', '=', self.product_id.id)])
            for param in params:
                for line in param.line_ids:
                    self.env['grn.qc.line'].create({
                        'qc_id': qc_id,
                        'product_id': self.product_id.id,
                        'name': line.name,
                        'specification': line.specification
                        })
        return True
    
    def _compute_grn(self):
        for move in self:
            if move.picking_id.picking_type_id and move.picking_id.picking_type_id.code == 'incoming':
                move.grn = True
                if move.product_id.qc_ok:
                    move.need_qc = True
                else:
                    move.need_qc = False
            else:
                move.grn = False
                move.need_qc = False
    
    @api.depends('qc_id', 'qc_id.state')
    def _compute_qc_status(self):
        for move in self:
            if move.qc_id:
                move.qc_status = move.qc_id.state
                
    qc_id = fields.Many2one('grn.qc', 'GRN QC', copy=False)
    qc_status = fields.Selection([
        ('pending', 'Pending'), ('ongoing', 'Ongoing'), ('completed', 'Completed')
        ], 'QC Status', compute='_compute_qc_status', store=True)
    grn = fields.Boolean('GRN', compute='_compute_grn')
    need_qc = fields.Boolean('QC Required', compute='_compute_grn')
    