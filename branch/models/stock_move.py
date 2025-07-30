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

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from itertools import groupby
from odoo.tools.misc import clean_context, OrderedSet, groupby
from collections import defaultdict
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class StockMoveLine(models.Model):
	_inherit = 'stock.move.line'
	
	def delete_sml_data(self):
		for sml in self:
			self._cr.execute('delete from stock_move_line where id=%s'% (sml.id))
		return True

	@api.model
	def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
		args = args or []
		user = self.env.user
		if 'no_branch_filter' in self._context:
			pass
		else:
			branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
			args += [('branch_id', 'in', branch_ids)]
		return super(StockMoveLine, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)

	@api.model
	def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
		domain = domain or []
		user = self.env.user
		if 'no_branch_filter' in self._context:
			pass
		else:
			branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
			domain += [('branch_id', 'in', branch_ids)]
		return super(StockMoveLine, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
	
	@api.depends('move_id', 'move_id.branch_id', 'move_id.state')
	def _get_branch(self):
		for line in self:
			line.branch_id = line.move_id and line.move_id.branch_id and line.move_id.branch_id.id or False

	branch_id = fields.Many2one('res.branch', 'Branch', compute='_get_branch', store=True)

	def _action_done(self):
		Quant = self.env['stock.quant']

		ml_ids_tracked_without_lot = OrderedSet()
		ml_ids_to_delete = OrderedSet()
		ml_ids_to_create_lot = OrderedSet()
		for ml in self:
			uom_qty = float_round(ml.qty_done, precision_rounding=ml.product_uom_id.rounding, rounding_method='HALF-UP')
			
			precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
			qty_done = float_round(ml.qty_done, precision_digits=precision_digits, rounding_method='HALF-UP')
			if float_compare(uom_qty, qty_done, precision_digits=precision_digits) != 0:
				raise UserError(_('The quantity done for the product "%s" doesn\'t respect the rounding precision '
								  'defined on the unit of measure "%s". Please change the quantity done or the '
								  'rounding precision of your unit of measure.') % (ml.product_id.display_name, ml.product_uom_id.name))

			qty_done_float_compared = float_compare(ml.qty_done, 0, precision_rounding=ml.product_uom_id.rounding)
			if qty_done_float_compared > 0:
				if ml.product_id.tracking != 'none':
					picking_type_id = ml.move_id.picking_type_id
					if picking_type_id:
						if picking_type_id.use_create_lots:
							if ml.lot_name and not ml.lot_id:
								lot = self.env['stock.lot'].search([
									('company_id', '=', ml.company_id.id),
									('product_id', '=', ml.product_id.id),
									('name', '=', ml.lot_name),
								], limit=1)
								if lot:
									ml.lot_id = lot.id
								else:
									ml_ids_to_create_lot.add(ml.id)
						elif not picking_type_id.use_create_lots and not picking_type_id.use_existing_lots:
							continue
					elif ml.is_inventory:
						continue

					if not ml.lot_id and ml.id not in ml_ids_to_create_lot:
						ml_ids_tracked_without_lot.add(ml.id)
			elif qty_done_float_compared < 0:
				raise UserError(_('No negative quantities allowed'))
			elif not ml.is_inventory:
				ml_ids_to_delete.add(ml.id)

#		if ml_ids_tracked_without_lot:
#			mls_tracked_without_lot = self.env['stock.move.line'].browse(ml_ids_tracked_without_lot)
#			raise UserError(_('You need to supply a Lot Number for product: \n - ') +
#							  '\n - '.join(mls_tracked_without_lot.mapped('product_id.display_name')))
		ml_to_create_lot = self.env['stock.move.line'].browse(ml_ids_to_create_lot)
		ml_to_create_lot.with_context(bypass_reservation_update=True)._create_and_assign_production_lot()

		mls_to_delete = self.env['stock.move.line'].browse(ml_ids_to_delete)
		mls_to_delete.unlink()

		mls_todo = (self - mls_to_delete)
		mls_todo._check_company()

		# Now, we can actually move the quant.
		ml_ids_to_ignore = OrderedSet()
		for ml in mls_todo:
			if ml.product_id.type == 'product':
				rounding = ml.product_uom_id.rounding

				# if this move line is force assigned, unreserve elsewhere if needed
				if not ml.move_id._should_bypass_reservation(ml.location_id) and float_compare(ml.qty_done, ml.reserved_uom_qty, precision_rounding=rounding) > 0:
					qty_done_product_uom = ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id, rounding_method='HALF-UP')
					extra_qty = qty_done_product_uom - ml.reserved_qty
					ml._free_reservation(ml.product_id, ml.location_id, extra_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, ml_ids_to_ignore=ml_ids_to_ignore)
				# unreserve what's been reserved
				if not ml.move_id._should_bypass_reservation(ml.location_id) and ml.product_id.type == 'product' and ml.reserved_qty:
					Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.reserved_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)

				# move what's been actually done
				quantity = ml.product_uom_id._compute_quantity(ml.qty_done, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
				available_qty, in_date = Quant.with_context(branch=ml.branch_id.id)._update_available_quantity(ml.product_id, ml.location_id, -quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
				if available_qty < 0 and ml.lot_id:
					# see if we can compensate the negative quants with some untracked quants
					untracked_qty = Quant.with_context(branch=ml.branch_id.id)._get_available_quantity(ml.product_id, ml.location_id, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
					if untracked_qty:
						taken_from_untracked_qty = min(untracked_qty, abs(quantity))
						Quant.with_context(branch=ml.branch_id.id)._update_available_quantity(ml.product_id, ml.location_id, -taken_from_untracked_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id)
						Quant.with_context(branch=ml.branch_id.id). _update_available_quantity(ml.product_id, ml.location_id, taken_from_untracked_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
				Quant.with_context(branch=ml.branch_id.id)._update_available_quantity(ml.product_id, ml.location_dest_id, quantity, lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id, in_date=in_date)
			ml_ids_to_ignore.add(ml.id)
		date = self._context.get('force_date', fields.Datetime.now())
		mls_todo.with_context(bypass_reservation_update=True).write({
			'reserved_uom_qty': 0.00,
			'date': date,
		    })

class StockMove(models.Model):
	_inherit = 'stock.move'
	
	@api.model
	def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
		args = args or []
		user = self.env.user
		if 'no_branch_filter' in self._context:
			pass
		else:
			branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
			args += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
		return super(StockMove, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)

	@api.model
	def _read_group_raw(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
		domain = domain or []
		user = self.env.user
		if 'no_branch_filter' in self._context:
			pass
		else:
			branch_ids = self._context.get('allowed_branch_ids', user.branch_ids.ids)
			domain += ['|', ('branch_id', '=', False), ('branch_id', 'in', branch_ids)]
		return super(StockMove, self)._read_group_raw(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
	
	branch_id = fields.Many2one('res.branch')

	@api.model
	def default_get(self, default_fields):
		res = super(StockMove, self).default_get(default_fields)
		if self.env.user.branch_id:
			res.update({
				'branch_id' : self.env.user.branch_id.id or False
				})
		return res

	def _get_new_picking_values(self):
		vals = super(StockMove, self)._get_new_picking_values()
		vals['branch_id'] = self.group_id.sale_id.branch_id.id
		return vals
	
