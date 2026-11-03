<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <div>
            <div class="stat-label">{{ t('restocking.budget') }}</div>
            <div class="budget-value">{{ money(budget) }}</div>
          </div>
          <button
            type="button"
            class="place-order-btn"
            :disabled="!canPlaceOrder"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>
        <input
          class="budget-slider"
          type="range"
          min="0"
          :max="maxBudget"
          step="100"
          :value="budget"
          :aria-label="t('restocking.budget')"
          @input="onBudgetInput"
        />
        <div class="slider-scale">
          <span>{{ money(0) }}</span>
          <span>{{ t('restocking.budgetMax') }}: {{ money(maxBudget) }}</span>
        </div>
      </div>

      <div v-if="successMessage" class="success-message" role="status">{{ successMessage }}</div>
      <div v-if="actionError" class="error" role="alert">{{ actionError }}</div>
      <div v-if="recError" class="error" role="alert">{{ recError }}</div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ money(totalCost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ money(remainingBudget) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.itemCount') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            {{ t('restocking.title') }} ({{ recommendations.length }})
            <span v-if="recLoading" class="updating">{{ t('restocking.updating') }}</span>
          </h3>
        </div>
        <div v-if="recommendations.length === 0 && !recLoading" class="empty-state">
          {{ t('restocking.empty') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.forecastedDemand') }}</th>
                <th class="num">{{ t('restocking.table.shortfall') }}</th>
                <th class="num">{{ t('restocking.table.recommendedQty') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ item.quantity_on_hand.toLocaleString() }}</td>
                <td class="num">{{ item.forecasted_demand.toLocaleString() }}</td>
                <td class="num">{{ item.shortfall.toLocaleString() }}</td>
                <td class="num">
                  <strong>{{ item.recommended_quantity.toLocaleString() }}</strong>
                  <span v-if="!item.fully_funded" class="badge warning partial">{{ t('restocking.partial') }}</span>
                </td>
                <td class="num">{{ money(item.unit_cost, 2) }}</td>
                <td class="num"><strong>{{ money(item.line_total) }}</strong></td>
                <td class="num">{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const { t, currentCurrency, translateProductName } = useI18n()

const DEBOUNCE_MS = 250
const STEP = 100
const INITIAL_FRACTION = 0.25

// Initial load (fetches the slider maximum)
const loading = ref(true)
const error = ref(null)

// Slider state. Amounts are always USD internally; money() converts for display.
const maxBudget = ref(0)
const budget = ref(0)

// Recommendation state
const recommendations = ref([])
const totalCost = ref(0)
const remainingBudget = ref(0)
const recLoading = ref(false)
const recError = ref(null)

// Order submission state
const submitting = ref(false)
const successMessage = ref(null)
const actionError = ref(null)

const canPlaceOrder = computed(() => recommendations.value.length > 0 && !submitting.value)

const money = (amount, decimals = 0) => {
  const value = Number(amount)
  const safe = Number.isFinite(value) ? value : 0
  return decimals > 0
    ? formatCurrencyWithDecimals(safe, currentCurrency.value, decimals)
    : formatCurrency(safe, currentCurrency.value)
}

let debounceTimer = null
// Monotonic id of the latest request; responses carrying an older id are ignored
// so a slow response for an earlier budget can never overwrite a newer one.
let requestSeq = 0

const loadRecommendations = async () => {
  const seq = ++requestSeq
  const requestedBudget = budget.value
  recLoading.value = true
  recError.value = null
  try {
    const data = await api.getRestockingRecommendations(requestedBudget)
    if (seq !== requestSeq) return // stale response
    recommendations.value = Array.isArray(data.recommendations) ? data.recommendations : []
    totalCost.value = data.total_cost ?? 0
    remainingBudget.value = data.remaining_budget ?? 0
  } catch (err) {
    if (seq !== requestSeq) return
    recError.value = t('restocking.loadError')
    console.error('Load error:', err)
  } finally {
    // Only the latest request controls the loading indicator
    if (seq === requestSeq) recLoading.value = false
  }
}

const scheduleLoad = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
}

// Driven by user input (not a watcher) so programmatic budget resets after an
// order don't clear the success message.
const onBudgetInput = (event) => {
  budget.value = Number(event.target.value)
  successMessage.value = null
  actionError.value = null
  scheduleLoad()
}

const placeOrder = async () => {
  if (!canPlaceOrder.value) return
  // Cancel any pending debounced fetch / ignore in-flight ones: the order must
  // match exactly what is displayed.
  clearTimeout(debounceTimer)
  submitting.value = true
  actionError.value = null
  successMessage.value = null
  try {
    const order = await api.createRestockingOrder({
      items: recommendations.value.map(r => ({ sku: r.sku, quantity: r.recommended_quantity })),
      budget: budget.value
    })
    successMessage.value = t('restocking.orderSuccess', {
      orderNumber: order.order_number,
      days: order.lead_time_days
    })
    // Reset: clear the plan and return the slider to 0 so the same order is not
    // accidentally placed twice.
    budget.value = 0
    ++requestSeq // invalidate in-flight fetches
    recommendations.value = []
    totalCost.value = 0
    remainingBudget.value = 0
    recLoading.value = false
  } catch (err) {
    const detail = err.response?.data?.detail
    actionError.value = `${t('restocking.orderError')}: ${typeof detail === 'string' ? detail : err.message}`
    console.error('Order error:', err)
  } finally {
    submitting.value = false
  }
}

const loadInitial = async () => {
  try {
    loading.value = true
    error.value = null
    // budget=0 returns no items but still reports full_restock_cost (slider max)
    const data = await api.getRestockingRecommendations(0)
    maxBudget.value = Number(data.full_restock_cost) || 0
    // ~25% of max, rounded to the slider step
    budget.value = Math.round((maxBudget.value * INITIAL_FRACTION) / STEP) * STEP
  } catch (err) {
    error.value = t('restocking.loadError')
    console.error('Load error:', err)
    return
  } finally {
    loading.value = false
  }
  await loadRecommendations()
}

onMounted(loadInitial)
onBeforeUnmount(() => {
  clearTimeout(debounceTimer)
  ++requestSeq
})
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.budget-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.625rem 1.25rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.success-message {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.updating {
  margin-left: 0.75rem;
  font-size: 0.813rem;
  font-weight: 400;
  color: #64748b;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

th.num,
td.num {
  text-align: right;
}

.partial {
  margin-left: 0.5rem;
}
</style>
