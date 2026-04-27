import type {
  BusinessScenario,
  MenuItem,
  Order,
  OrderItem,
} from './types.ts'

const MENU: MenuItem[] = [
  { id: 'latte', name: 'Latte', category: 'Coffee', priceCents: 425, unitCostCents: 136, kind: 'coffee_shop' },
  { id: 'cold-brew', name: 'Cold Brew', category: 'Coffee', priceCents: 475, unitCostCents: 166, kind: 'coffee_shop' },
  { id: 'croissant', name: 'Croissant', category: 'Pastry', priceCents: 450, unitCostCents: 126, kind: 'shared' },
  { id: 'breakfast-burrito', name: 'Breakfast Burrito', category: 'Food', priceCents: 875, unitCostCents: 350, kind: 'coffee_shop' },
  { id: 'chicken-sandwich', name: 'Chicken Sandwich', category: 'Entree', priceCents: 1550, unitCostCents: 682, kind: 'restaurant' },
  { id: 'grain-bowl', name: 'Grain Bowl', category: 'Entree', priceCents: 1425, unitCostCents: 499, kind: 'restaurant' },
  { id: 'fries', name: 'Fries', category: 'Side', priceCents: 625, unitCostCents: 125, kind: 'restaurant' },
  { id: 'dessert', name: 'Chocolate Cake', category: 'Dessert', priceCents: 825, unitCostCents: 248, kind: 'restaurant' },
]

const SCENARIOS: BusinessScenario[] = [
  buildScenario({
    id: 'coffee_pilsen_evening_gap',
    label: 'Coffee shop in Pilsen with uncaptured evening demand',
    business: {
      id: 'biz-coffee-pilsen',
      name: 'Cafe Con Leche',
      kind: 'coffee_shop',
      neighborhood: 'Pilsen',
      address: '1801 S Blue Island Ave',
      currency: 'USD',
    },
    menuItemIds: ['latte', 'cold-brew', 'croissant', 'breakfast-burrito'],
    orderPattern: [
      { hour: 8, count: 18, itemIds: ['latte', 'croissant'] },
      { hour: 10, count: 12, itemIds: ['latte'] },
      { hour: 13, count: 10, itemIds: ['cold-brew', 'breakfast-burrito'] },
      { hour: 18, count: 8, itemIds: ['latte'] },
      { hour: 19, count: 7, itemIds: ['cold-brew'] },
    ],
    openMinute: 6 * 60 + 30,
    closeMinute: 20 * 60,
    inventory: [{ menuItemId: 'croissant', date: '2026-05-15', stockoutHour: 11, unitsRemaining: 0 }],
    eveningDemandIndex: 86,
    inspectionPressure: 'medium',
  }),
  buildScenario({
    id: 'restaurant_pilsen_margin_leak',
    label: 'Restaurant in Pilsen with low-margin mix',
    business: {
      id: 'biz-restaurant-pilsen',
      name: 'Canal Street Kitchen',
      kind: 'restaurant',
      neighborhood: 'Pilsen',
      address: '1720 S Halsted St',
      currency: 'USD',
    },
    menuItemIds: ['chicken-sandwich', 'grain-bowl', 'fries', 'dessert'],
    orderPattern: [
      { hour: 12, count: 18, itemIds: ['chicken-sandwich'] },
      { hour: 13, count: 14, itemIds: ['chicken-sandwich', 'fries'] },
      { hour: 18, count: 16, itemIds: ['grain-bowl'] },
      { hour: 19, count: 18, itemIds: ['chicken-sandwich'] },
      { hour: 20, count: 10, itemIds: ['grain-bowl', 'dessert'] },
    ],
    openMinute: 11 * 60,
    closeMinute: 21 * 60,
    inventory: [],
    eveningDemandIndex: 68,
    inspectionPressure: 'medium',
  }),
  buildScenario({
    id: 'restaurant_inspection_risk',
    label: 'Restaurant with compliance pressure',
    business: {
      id: 'biz-restaurant-risk',
      name: '18th Street Grill',
      kind: 'restaurant',
      neighborhood: 'Pilsen',
      address: '1642 W 18th St',
      currency: 'USD',
    },
    menuItemIds: ['chicken-sandwich', 'grain-bowl', 'fries', 'dessert'],
    orderPattern: [
      { hour: 12, count: 12, itemIds: ['grain-bowl'] },
      { hour: 13, count: 10, itemIds: ['chicken-sandwich', 'fries'] },
      { hour: 18, count: 14, itemIds: ['grain-bowl', 'dessert'] },
      { hour: 19, count: 12, itemIds: ['chicken-sandwich'] },
      { hour: 20, count: 8, itemIds: ['chicken-sandwich'], refundEvery: 4 },
    ],
    openMinute: 11 * 60,
    closeMinute: 21 * 60,
    inventory: [{ menuItemId: 'dessert', date: '2026-05-15', stockoutHour: 20, unitsRemaining: 0 }],
    eveningDemandIndex: 66,
    inspectionPressure: 'high',
  }),
]

export const MOCK_POS_SCENARIO_IDS = SCENARIOS.map(scenario => scenario.id)

export function getBusinessScenario(id = SCENARIOS[0].id): BusinessScenario {
  return SCENARIOS.find(item => item.id === id) ?? SCENARIOS[0]
}

export function listBusinessScenarios(): Array<{ id: string; label: string; kind: string; neighborhood: string }> {
  return SCENARIOS.map(({ id, label, business }) => ({
    id,
    label,
    kind: business.kind,
    neighborhood: business.neighborhood,
  }))
}

interface ScenarioSeed {
  id: string
  label: string
  business: BusinessScenario['business']
  menuItemIds: string[]
  orderPattern: Array<{ hour: number; count: number; itemIds: string[]; refundEvery?: number }>
  openMinute: number
  closeMinute: number
  inventory: BusinessScenario['inventorySignals']
  eveningDemandIndex: number
  inspectionPressure: BusinessScenario['neighborhoodContext']['inspectionPressure']
}

function buildScenario(seed: ScenarioSeed): BusinessScenario {
  const menuItems = MENU.filter(item => seed.menuItemIds.includes(item.id))
  const menuById = new Map(menuItems.map(item => [item.id, item]))
  const orders: Order[] = []
  const orderItems: OrderItem[] = []

  for (let dayOffset = 0; dayOffset < 7; dayOffset += 1) {
    const date = new Date(Date.UTC(2026, 4, 9 + dayOffset))
    seed.orderPattern.forEach(pattern => {
      for (let index = 0; index < pattern.count; index += 1) {
        const openedAt = new Date(date)
        openedAt.setUTCHours(pattern.hour, (index * 6) % 60, 0, 0)
        const orderId = `ord-${seed.id}-${dayOffset}-${pattern.hour}-${index}`
        const gross = pattern.itemIds.reduce((sum, id) => sum + (menuById.get(id)?.priceCents ?? 0), 0)
        orders.push({
          id: orderId,
          openedAt: openedAt.toISOString(),
          totalCents: gross,
          refundCents: pattern.refundEvery && index % pattern.refundEvery === 0 ? Math.round(gross * 0.35) : 0,
        })
        pattern.itemIds.forEach((menuItemId, itemIndex) => {
          orderItems.push({
            id: `item-${orderId}-${itemIndex}`,
            orderId,
            menuItemId,
            quantity: 1,
            grossCents: menuById.get(menuItemId)?.priceCents ?? 0,
          })
        })
      }
    })
  }

  return {
    id: seed.id,
    label: seed.label,
    business: seed.business,
    menuItems,
    orders,
    orderItems,
    operatingHours: [1, 2, 3, 4, 5, 6, 0].map(dayOfWeek => ({
      dayOfWeek,
      openMinute: seed.openMinute,
      closeMinute: seed.closeMinute,
    })),
    inventorySignals: seed.inventory,
    neighborhoodContext: {
      eveningDemandIndex: seed.eveningDemandIndex,
      inspectionPressure: seed.inspectionPressure,
    },
  }
}
