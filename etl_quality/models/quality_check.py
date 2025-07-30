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
    
class GrnQc(models.Model):
    _name = 'grn.qc'
    _description = 'GRN QC'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    
    @api.depends('picking_id', 'picking_id.name', 'picking_id.origin', 'picking_id.partner_id')
    def _compute_name(self):
        for param in self:
            if param.picking_id:
                pos = self.env['purchase.order'].search([('name', '=', param.picking_id.origin)])
                purchase_id = pos and pos[0].id or False
                param.name = param.picking_id.name
                param.purchase_id = purchase_id
                param.partner_id = param.picking_id.partner_id.id
            else:
                param.name = ''
                param.purchase_id = False
                param.partner_id = False
    
    name = fields.Char('Name', compute='_compute_name', store=True)
    picking_id = fields.Many2one('stock.picking', 'GRN')
    purchase_id = fields.Many2one('purchase.order', 'Purchase Order', compute='_compute_name', store=True)
    partner_id = fields.Many2one('res.partner', 'Vendor', compute='_compute_name', store=True)
    line_ids = fields.One2many('grn.qc.line', 'qc_id', 'Lines')
    date = fields.Date('Date')
    state = fields.Selection([
        ('pending', 'Pending'), ('ongoing', 'Ongoing'), ('completed', 'Completed')
        ], 'Status', default='pending', tracking=True)
    remarks = fields.Char('Remarks', tracking=True)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    accept_qty = fields.Float('Accept Qty', digits=(16, 3))
    reject_qty = fields.Float('Reject Qty', digits=(16, 3))
    grn_qty = fields.Float(string='GRN Qty')
    
    def action_reset(self):
        self.state = 'ongoing'
        
    def action_ongoing(self):
        self.state = 'ongoing'
    
    def action_completed(self):
        for line in self.line_ids:
            if not line.result:
                raise UserError('Cannot complete QC Check without entering Result!')
        if not self.accept_qty and not self.reject_qty:
            raise UserError('Please enter Accept Qty / Reject Qty')
        self.state = 'completed'

    def action_print_grn_qc(self):
        return self.env.ref('etl_quality.action_report_grn_qc').report_action(self)

    def _compute_grn_qty(self):
        for param in self:
            qty = 0
            if param.picking_id:
                grn = self.env['stock.move'].search([
                    ('picking_id', '=', param.picking_id.id),
                    ('product_id', '=', param.product_id.id)
                    ])
                qty = grn.product_uom_qty
            param.grn_qty = qty

        
class GrnQcLines(models.Model):
    _name = 'grn.qc.line'
    _description = 'GRN QC Lines'
    
    categ_id = fields.Many2one('product.category', 'Product Category', required=False)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    name = fields.Char('Parameter')
    qc_id = fields.Many2one('grn.qc', 'GRN QC')
    result = fields.Selection([('passed', 'Passed'), ('failed', 'Failed')], 'Test Result')
    specification = fields.Char('Specification')
    result_value = fields.Char('Result Value')

class MOQc(models.Model):
    _name = 'mo.qc'
    _description = 'MO QC'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    
    @api.depends('production_id', 'production_id.name')
    def _compute_name(self):
        for param in self:
            if param.production_id:
                param.name = param.production_id.name
                param.product_id = param.production_id.product_id.id
            else:
                param.name = ''
                param.product_id = False
            
    name = fields.Char('Name', compute='_compute_name', store=True)
    production_id = fields.Many2one('mrp.production', 'MO')
    product_id = fields.Many2one('product.product', 'Product', compute='_compute_name', store=True)
    line_ids = fields.One2many('mo.qc.line', 'qc_id', 'Lines')
    date = fields.Date('Date')
    state = fields.Selection([
        ('pending', 'Pending'), ('ongoing', 'Ongoing'), ('completed', 'Completed')
        ], 'Status', default='pending', tracking=True)
    accept_qty = fields.Float('Accept Qty', digits=(16, 3))
    reject_qty = fields.Float('Reject Qty', digits=(16, 3))
    remarks = fields.Char('Remarks', tracking=True)
    
    def action_ongoing(self):
        self.state = 'ongoing'
    
    def action_completed(self):
        for line in self.line_ids:
            if not line.result:
                raise UserError('Cannot complete QC Check without entering Result!')
        self.state = 'completed'

    def action_print_mo_qc(self):
        return self.env.ref('etl_quality.action_report_mo_qc').report_action(self)


class MOQcLines(models.Model):
    _name = 'mo.qc.line'
    _description = 'MO QC Lines'
    
    name = fields.Char('Parameter Name')
    remark = fields.Char('Remarks')
    qc_id = fields.Many2one('mo.qc', 'MO QC')
    result = fields.Selection([('passed', 'Passed'), ('failed', 'Failed')], 'Test Result')
    specification = fields.Char('Specification')
    result_value = fields.Char('Result Value')
    
    