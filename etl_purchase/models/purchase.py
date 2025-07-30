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

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    
    @api.depends('partner_id', 'partner_id.is_branch')
    def _check_branch(self):
        for order in self:
            order.branch_purchase = order.partner_id.is_branch
    
    READONLY_STATES = {
        'purchase': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
        }
    
    po_type = fields.Selection([
        ('service', 'Engineering Purchase'),
        ('service_po', 'Service Purchase'),
        ('stock', 'Stock Transfer Purchase'),
        ('internal', 'Internal Transfer'),
        ('import', 'Import Purchase'),
        ('domestic', 'Domestic Purchase'),
        ('sub_con', 'Subcon Purchase'),
        ('packing', 'Packing Material Purchase'),
        ], 'Purchase Order Type')
    notes = fields.Html('Terms and Conditions', default=lambda self: self.env.company.po_tnc)
    required_date = fields.Date('Required Date')
    approval_id = fields.Many2one('approval.request', 'Approval Request')
    branch_purchase = fields.Boolean(compute='_check_branch', store=True)
    fiscal_year = fields.Char('Fiscal Year', compute='_compute_fiscal_year', store=True)
    state = fields.Selection(selection_add=[
        ('draft', 'RFQ'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled')
        ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    login_user_id = fields.Many2one('res.users', compute='_login_user')
    date_order = fields.Datetime('Order Date', required=True, states=READONLY_STATES, 
        index=True, copy=False, default=fields.Datetime.now)
    
    def _login_user(self):
        for move in self:
            move.login_user_id = self.env.user.user_access and self.env.user.id or False
            
    @api.depends('state', 'date_order')
    def _compute_fiscal_year(self):
        for order in self:
            fiscal_year = ''
            if order.date_order:
                fy = order.company_id.compute_fiscalyear_dates(order.date_order)
                fiscal_year = fy['date_from'].strftime('%y') + fy['date_to'].strftime('%y')
            order.fiscal_year = fiscal_year
            
    @api.model_create_multi
    def create(self, vals_list):
        order = super().create(vals_list)
        seq_prefix = 'PO/%s/%s'%(order.fiscal_year, order.branch_id.code)
        prev_orders = self.with_context(no_filter=True).search([
            ('branch_id', '=', order.branch_id.id),
            ('fiscal_year', '=', order.fiscal_year),
            ('id', '!=', order.id),
            ('name', 'ilike', seq_prefix)
            ], order='name desc', limit=1)
        
        if prev_orders:
            prev_name = prev_orders[0].name
            if seq_prefix in prev_name:
                name_split = prev_name.split('/')[-1]
                sequence_number = int(name_split)+1
            else:
                sequence_number = 1
        else:
            sequence_number = 1
        
        name = '%s/%s'%(seq_prefix, str(sequence_number).zfill(4))
        order.name = name
        sequence = 1
        for line in order.order_line:
            line.sequence = sequence
            sequence += 1
        return order
    
    def action_view_picking(self):
        res = self._get_action_view_picking(self.picking_ids)
        for order in self:
            for picking in order.picking_ids:
                for move in picking.move_ids_without_package:
                    if move.purchase_line_id:
                        purchase_line = move.purchase_line_id
                        move.write({
                            'alt_uom_id': purchase_line.alt_uom_id and purchase_line.alt_uom_id.id or False,
                            'sequence': purchase_line.sequence,
                            'alt_uom_qty': purchase_line.alt_uom_qty
                            })
        return res
    
    def _approval_allowed(self):
        self.ensure_one()
        if self.company_id.po_double_validation == 'one_step':
            return True
        return False
    
    def button_approve_cfo(self):
        self.button_approve()
        return {}
    
    def button_approve_po(self):
        if self.po_type == 'stock':
            if not self.user_has_groups('etl_base.group_purchase_cfo'):
                raise UserError('Only CFO can approve Stock Transfer Orders !')
            self.button_approve()
        else:
            company = self.company_id
            po_limit = company.po_double_validation_amount
            po_amount = self.amount_total
            if company.currency_id.id != self.currency_id.id:
                po_amount = company.currency_id._convert(po_amount, self.currency_id, self.company_id, self.date_order or fields.Date.today())
            if po_amount >= po_limit:
                if not self.user_has_groups('etl_base.group_purchase_cfo'):
                    raise UserError('Only CFO can approve PO with Value >= 2 Lakhs !')
                self.button_approve()
            else:
                if self.user_has_groups('etl_base.group_purchase_pm'):
                    self.button_approve()
        return True
    
    def button_approve(self, force=False):
        self.write({'state': 'purchase', 'date_approve': fields.Datetime.now()})
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        self._create_picking()
        if self.po_type == 'stock':
            self.create_so()
        return {}
    
    def create_so(self):
        for order in self:
            if not order.fiscal_position_id:
                raise UserError('Please select Fiscal Position.')
            vendor_branch_ids = self.env['res.branch'].with_context(no_filter=True).search([('partner_id', '=', order.partner_id.id)])
            vendor_branch_id = vendor_branch_ids and vendor_branch_ids[0].id or False
            branched_warehouses = self.env['stock.warehouse'].with_context(no_filter=True).search([('branch_id', '=', vendor_branch_id)])
            line_vals = []
            for line in order.order_line:
                line_vals.append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_qty,
                    'price_unit': line.price_unit,
                    'alt_uom_id': line.alt_uom_id and line.alt_uom_id.id or False,
                    'alt_uom_qty': line.alt_uom_qty,
                    'remarks': line.remarks,
                    'sequence': line.sequence
                    }))
            order_vals = {
                'partner_id': self.branch_id.partner_id.id,
                'branch_id': vendor_branch_id,
                'warehouse_id': branched_warehouses and branched_warehouses[0].id or False,
                'order_line': line_vals,
                'origin': self.name,
                'so_type': self.po_type,
                'fiscal_position_id': order.fiscal_position_id.id
                }
            self.env['sale.order'].sudo().create(order_vals)
        return True
    
    def button_confirm(self):
        res = super(PurchaseOrder, self).button_confirm()
        return res
    
    def action_view_approval(self):
        approval_id = False
        if self.approval_id:
            approval_id = self.approval_id.id
        elif self.origin:
            approvals = self.env['approval.request'].search([('name', '=', self.origin)])
            if approvals:
                approval_id = approvals[0].id
        if approval_id:
            result = self.env['ir.actions.act_window']._for_xml_id('approvals.approval_request_action_all')
            res = self.env.ref('approvals.approval_request_view_form', False)
            form_view = [(res and res.id or False, 'form')]
            result['views'] = form_view
            result['res_id'] = approval_id
        else:
            result = {'type': 'ir.actions.act_window_close'}
        return result
    
    def button_create_picking(self):
        if self.incoming_picking_count == 0:
            self._create_picking()
        return True
    
    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for order in self.filtered(lambda po: po.state in ('purchase', 'done')):
            if any(product.type in ['product', 'consu'] for product in order.order_line.product_id):
                order = order.with_company(order.company_id)
                pickings = order.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
                if not pickings:
                    res = order._prepare_picking()
                    picking = StockPicking.with_user(SUPERUSER_ID).create(res)
                    pickings = picking
                else:
                    picking = pickings[0]
                moves = order.order_line._create_stock_moves(picking)
                moves = moves.filtered(lambda x: x.state not in ('done', 'cancel'))._action_confirm()
                moves._action_assign()
                forward_pickings = self.env['stock.picking']._get_impacted_pickings(moves)
                (pickings | forward_pickings).action_confirm()
                picking.message_post_with_view('mail.message_origin_link',
                    values={'self': picking, 'origin': order},
                    subtype_id=self.env.ref('mail.mt_note').id)
        return True
    
class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    
    def _check_editing_access(self):
        if self.user_has_groups('etl_base.group_poprice_editing'):
            return True
        else:
            return False
        
    alt_uom_id = fields.Many2one('product.alt.uom', 'Package Name')
    alt_uom_qty = fields.Integer('Package Qty', default=1)
    alt_uom_qty_received = fields.Integer('Package Qty', compute='_compute_rec_qty')
    remarks = fields.Char('Remarks')
    sequence = fields.Integer("Sequence", default=1)
    sl_no = fields.Integer("SL No.", compute='_compute_sl_no', store=True)
    current_stock = fields.Float('On Hand Qty')
    avg_sales_qty = fields.Float('Monthly Avg. Sales')
    allow_unitprice_editing = fields.Boolean('Allow UnitPrice Editing', compute='_check_unitprice_access',
        default=_check_editing_access)
    
    def _check_unitprice_access(self):
        for line in self:
            allow_editing = False
            if self.user_has_groups('etl_base.group_poprice_editing'):
                allow_editing = True
            line.allow_unitprice_editing = allow_editing
    
    def name_get(self):
        return [(line.id, '(%s)-%s' % (line.order_id.name, line.name)) for line in self]
    
    @api.onchange('product_id')
    def _compute_stock(self):
        if self.product_id and self.order_id.po_type == 'stock':
            branch_id = self.order_id.branch_id.id
            location_ids = self.env['stock.location'].search([
                ('usage', '=', 'internal'),
                ('branch_id', '=', branch_id)
                ]).ids
            quants = self.env['stock.quant'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', 'in', location_ids)
                ])
            self.current_stock = sum([quant.available_quantity for quant in quants])
        
    @api.depends('sequence')
    def _compute_sl_no(self):
        for line in self:
            line.sl_no = line.sequence
    
    def _prepare_stock_move_vals(self, picking, price_unit, product_uom_qty, product_uom):
        res = super(PurchaseOrderLine, self)._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom)
        vals = {
            'alt_uom_id': self.alt_uom_id and self.alt_uom_id.id or False,
            'alt_uom_qty': self.alt_uom_qty,
            'sequence': self.sequence
            }
        res.update(vals)
        return res
        
    @api.onchange('product_id', 'alt_uom_id', 'alt_uom_qty')
    def onchange_alt_uom(self):
        if self.product_id:
            if not self.alt_uom_id:
                self.alt_uom_id = self.product_id.product_tmpl_id.alt_uom_id.id
            template = self.product_id.product_tmpl_id
            if self.alt_uom_id.type == 'base':
                self.product_qty = template.weight_bag * self.alt_uom_qty
            elif self.alt_uom_id.type == 'smaller':
                self.product_qty = template.weight_belt * self.alt_uom_qty
        else:
            self.product_qty = 0
    
