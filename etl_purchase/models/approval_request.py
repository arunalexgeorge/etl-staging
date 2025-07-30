# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import calendar

class ApprovalCategory(models.Model):
    _inherit = 'approval.category'
    
    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To')
    
class ApprovalRequest(models.Model):
    _inherit = 'approval.request'
    
    def _default_allow_editing(self):
        if self.env.user.has_group('etl_base.group_approval_edit'):
            return True
        else:
            return False
    
    def _compute_allow_editing(self):
        for line in self:
            if self.env.user.has_group('etl_base.group_approval_edit'):
                line.allow_editing = True
            else:
                line.allow_editing = False
    
    @api.onchange('category_id')    
    def _get_default_picking_type(self):
        if self.category_id:
            self.picking_type_id = self.category_id.picking_type_id and self.category_id.picking_type_id.id or False
        else:
            self.picking_type_id = False
    
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
            args += ['|', ('branch_id', '=', False), ('branch_id', 'in', branches_ids)]
        return super(ApprovalRequest, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
    
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
            domain += ['|', ('branch_id', '=', False), ('branch_id', 'in', branches_ids)]
        return super(ApprovalRequest, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
    
    @api.model
    def default_get(self, default_fields):
        res = super(ApprovalRequest, self).default_get(default_fields)
        branch_id = False
        if self._context.get('branch_id'):
            branch_id = self._context.get('branch_id')
        elif self.env.user.branch_id:
            branch_id = self.env.user.branch_id.id
        res.update({'branch_id' : branch_id})
        return res
    
    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        category = res.category_id
        seq_prefix = '%s/%s/%s'%(category.sequence_code, res.fiscal_year, res.branch_id.code)
        prev_orders = self.with_context(no_filter=True).search([
            ('branch_id', '=', res.branch_id.id),
            ('fiscal_year', '=', res.fiscal_year),
            ('id', '!=', res.id),
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
        res.name = name
        return res
    
    name = fields.Char(string="Approval Subject", tracking=True, default='/')
    branch_id = fields.Many2one('res.branch', "Branch")
    po_type = fields.Selection([
        ('service', 'Service Purchase'),
        ('stock', 'Stock Transfer Purchase'),
        ('import', 'Import Purchase'),
        ('domestic', 'Domestic Purchase'),
        ], 'Purchase Order Type', tracking=True)
    date = fields.Date('Material Required Date')
    allow_editing = fields.Boolean('Allow Editing', compute='_compute_allow_editing',
        default=_default_allow_editing)
    picking_type_id = fields.Many2one('stock.picking.type', 'Deliver To')
    fiscal_year = fields.Char('Fiscal Year', compute='_compute_fiscal_year', store=True)
    
    @api.depends('create_date')
    def _compute_fiscal_year(self):
        for approval in self:
            fiscal_year = ''
            if approval.create_date:
                fy = approval.company_id.compute_fiscalyear_dates(approval.create_date)
                fiscal_year = fy['date_from'].strftime('%y') + fy['date_to'].strftime('%y')
            approval.fiscal_year = fiscal_year
            
    def action_create_purchase_orders(self):
        vendor_list = []
        if not self.picking_type_id:
            raise UserError("Enter Deliver To")
        for line in self.product_line_ids:
            if not line.partner_id:
                raise UserError("Enter Vendor for all lines")
            if line.partner_id.id not in vendor_list:
                vendor_list.append(line.partner_id.id)
        vendor_list = list(set(vendor_list))
        for vendor_id in vendor_list:
            po_line_vals = []
            po_vals = {
                'partner_id': vendor_id,
                'origin': self.name,
                'po_type': self.po_type,
                'required_date': self.date,
                'approval_id': self.id,
                'picking_type_id': self.picking_type_id.id
                }
            new_purchase_order = self.env['purchase.order'].create(po_vals)
            for line in self.product_line_ids:
                if line.partner_id.id == vendor_id:
                    name = line.product_id.name_get()[0][1]
                    product_taxes = line.product_id.supplier_taxes_id
                    line_vals = {
                        'name': name,
                        'product_qty': line.quantity,
                        'product_id': line.product_id.id,
                        'product_uom': line.product_id.uom_po_id.id,
                        'price_unit': line.vendor_price,
                        'taxes_id': [(6, 0, product_taxes.ids)],
                        'order_id': new_purchase_order.id
                        }
                    purchase_order_line = self.env['purchase.order.line'].create(line_vals)
                    line.purchase_order_line_id = purchase_order_line.id
                    
class ApprovalProductLine(models.Model):
    _inherit = 'approval.product.line'
    
    def _default_allow_editing(self):
        if self.env.user.has_group('etl_base.group_approval_edit'):
            return True
        else:
            return False
    
    def _compute_allow_editing(self):
        for line in self:
            if self.env.user.has_group('etl_base.group_approval_edit'):
                line.allow_editing = True
            else:
                line.allow_editing = False
    
    @api.depends('approval_request_id.request_status')
    def _compute_request_status(self):
        for line in self:
            line.state = line.approval_request_id.request_status
    
    partner_id = fields.Many2one('res.partner', 'Vendor')
    vendor_price = fields.Float('Price')
    current_stock = fields.Float('Current Stock')
    consumption_qty = fields.Float('Last Month Consumption')
    allow_editing = fields.Boolean('Allow Editing', compute='_compute_allow_editing',
        default=_default_allow_editing)
    state = fields.Selection([
        ('new', 'To Submit'),
        ('pending', 'Submitted'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancel', 'Cancel'),
        ], compute="_compute_request_status", store=True,
        default='new')
    
    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.product_id and self.partner_id:
            product_tmpl_id = self.env['product.product'].browse(self.product_id.id).product_tmpl_id.id
            supp_infos = self.env['product.supplierinfo'].search([
                ('product_tmpl_id', '=', product_tmpl_id),
                ('partner_id', '=', self.partner_id.id)
                ])
            if supp_infos:
                self.vendor_price = supp_infos[0].price
    
    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.current_stock = self.product_id.qty_available
            last_month = fields.Date.today() - relativedelta(months=1)
            start_date = last_month.strftime('%Y-%m-01')
            end_date = fields.Date.today().strftime('%Y-%m-01')
            conus_out_moves = self.env['stock.move'].search([
                ('product_id', '=', self.product_id.id),
                ('state', '=', 'done'),
                ('date', '<', end_date),
                ('date', '>=', start_date),
                ('location_dest_id', '=', 15),
                ])
            out_qty = sum([move.product_uom_qty for move in conus_out_moves])
            conus_in_moves = self.env['stock.move'].search([
                ('product_id', '=', self.product_id.id),
                ('state', '=', 'done'),
                ('date', '<', end_date),
                ('date', '>=', start_date),
                ('location_id', '=', 15),
                ])
            in_qty = sum([move.product_uom_qty for move in conus_in_moves])
            self.consumption_qty = out_qty - in_qty
            product_tmpl_id = self.env['product.product'].browse(self.product_id.id).product_tmpl_id.id
            supp_infos = self.env['product.supplierinfo'].search([
                ('product_tmpl_id', '=', product_tmpl_id),
                ])
            if supp_infos:
                self.partner_id = supp_infos[0].partner_id.id
                self.vendor_price = supp_infos[0].price
            else:
                self.partner_id = False
                self.vendor_price = 0
        
class Partner(models.Model):
    _inherit = 'res.partner'
    
    # @api.model
    # def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
    #     args = args or []
    #     domain =  []
    #
    #     if 'product_id' in self._context and self._context['product_id']:
    #         product_tmpl_id = self.env['product.product'].browse(self._context['product_id']).product_tmpl_id.id
    #         partner_ids = []
    #         supp_infos = self.env['product.supplierinfo'].search([('product_tmpl_id', '=', product_tmpl_id)])
    #         if supp_infos:
    #             for supp_info in supp_infos:
    #                 partner_ids.append(supp_info.partner_id.id)
    #         args += [('id', 'in', partner_ids)]
    #         return super(Partner, self)._name_search(name=name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid)
    #     return super(Partner, self)._name_search(name=name, args=args, operator=operator, limit=limit,name_get_uid=name_get_uid)
    