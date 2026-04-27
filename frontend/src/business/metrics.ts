import type { BusinessMetrics, BusinessScenario, Daypart, MenuItem, Order, ProductMetric } from './types.ts'

const TODAY = '2026-05-15'
const DAYPARTS: Daypart[] = ['morning', 'lunch', 'afternoon', 'dinner', 'evening']

export function computeBusinessMetrics(scenario: BusinessScenario): BusinessMetrics {
  const menuById = new Map(scenario.menuItems.map(item => [item.id, item]))
  const ordersById = new Map(scenario.orders.map(order => [order.id, order]))
  const todayOrders = scenario.orders.filter(order => order.openedAt.startsWith(TODAY))
  const weekOrders = scenario.orders.filter(order => isWithinLastSevenDays(order.openedAt))
  const productMetrics = computeProductMetrics(scenario, menuById, ordersById)
  const daypartRevenueCents = computeDaypartRevenue(todayOrders)
  const grossProfitCents = productMetrics.reduce((sum, item) => sum + item.grossProfitCents, 0)
  const revenueCents = weekOrders.reduce((sum, order) => sum + netOrderRevenue(order), 0)
  const topHighMarginIds = new Set(
    productMetrics
      .filter(item => item.marginPct >= 65)
      .map(item => item.menuItemId),
  )
  const highMarginOrderCount = todayOrders.filter(order =>
    scenario.orderItems.some(item => item.orderId === order.id && topHighMarginIds.has(item.menuItemId)),
  ).length

  return {
    businessId: scenario.business.id,
    scenarioId: scenario.id,
    todayRevenueCents: todayOrders.reduce((sum, order) => sum + netOrderRevenue(order), 0),
    projectedWeekRevenueCents: Math.round(revenueCents * (7 / Math.max(1, countUniqueDays(weekOrders)))),
    grossProfitCents,
    averageOrderValueCents: todayOrders.length > 0
      ? Math.round(todayOrders.reduce((sum, order) => sum + netOrderRevenue(order), 0) / todayOrders.length)
      : 0,
    orderCount: todayOrders.length,
    refundRatePct: pct(
      todayOrders.reduce((sum, order) => sum + order.refundCents, 0),
      todayOrders.reduce((sum, order) => sum + order.totalCents, 0),
    ),
    productMetrics,
    daypartRevenueCents,
    highMarginAttachRatePct: pct(highMarginOrderCount, Math.max(1, todayOrders.length)),
    stockoutRiskItems: scenario.inventorySignals
      .filter(signal => signal.stockoutHour !== null || signal.unitsRemaining <= 5)
      .map(signal => menuById.get(signal.menuItemId)?.name)
      .filter((name): name is string => Boolean(name)),
  }
}

function computeProductMetrics(
  scenario: BusinessScenario,
  menuById: Map<string, MenuItem>,
  ordersById: Map<string, Order>,
): ProductMetric[] {
  const metrics = new Map<string, ProductMetric>()

  scenario.orderItems.forEach(orderItem => {
    const menuItem = menuById.get(orderItem.menuItemId)
    const order = ordersById.get(orderItem.orderId)
    if (!menuItem || !order || !isWithinLastSevenDays(order.openedAt)) return

    const current = metrics.get(menuItem.id) ?? {
      menuItemId: menuItem.id,
      name: menuItem.name,
      category: menuItem.category,
      revenueCents: 0,
      grossProfitCents: 0,
      unitsSold: 0,
      marginPct: 0,
    }
    current.revenueCents += orderItem.grossCents
    current.grossProfitCents += (menuItem.priceCents - menuItem.unitCostCents) * orderItem.quantity
    current.unitsSold += orderItem.quantity
    current.marginPct = pct(current.grossProfitCents, current.revenueCents)
    metrics.set(menuItem.id, current)
  })

  return [...metrics.values()].sort((a, b) => b.revenueCents - a.revenueCents)
}

function computeDaypartRevenue(orders: Order[]): Record<Daypart, number> {
  const revenue = Object.fromEntries(DAYPARTS.map(daypart => [daypart, 0])) as Record<Daypart, number>
  orders.forEach(order => {
    revenue[toDaypart(new Date(order.openedAt).getUTCHours())] += netOrderRevenue(order)
  })
  return revenue
}

function toDaypart(hour: number): Daypart {
  if (hour < 11) return 'morning'
  if (hour < 14) return 'lunch'
  if (hour < 17) return 'afternoon'
  if (hour < 21) return 'dinner'
  return 'evening'
}

function isWithinLastSevenDays(isoDate: string): boolean {
  const time = new Date(isoDate).getTime()
  const start = Date.UTC(2026, 4, 9)
  const end = Date.UTC(2026, 4, 16)
  return time >= start && time < end
}

function countUniqueDays(orders: Order[]): number {
  return new Set(orders.map(order => order.openedAt.slice(0, 10))).size
}

function netOrderRevenue(order: Order): number {
  return Math.max(0, order.totalCents - order.refundCents)
}

function pct(numerator: number, denominator: number): number {
  if (denominator === 0) return 0
  return Math.round((numerator / denominator) * 1000) / 10
}
