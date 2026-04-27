<script setup>
import UiBadge from './UiBadge.vue'
import UiCard from './UiCard.vue'

defineProps({
  eyebrow: {
    type: String,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  lead: {
    type: String,
    required: true,
  },
  heroLabel: {
    type: String,
    required: true,
  },
  heroTitle: {
    type: String,
    required: true,
  },
  heroDescription: {
    type: String,
    default: '',
  },
  statusLabel: {
    type: String,
    default: '',
  },
  statusVariant: {
    type: String,
    default: 'secondary',
  },
  networkLabel: {
    type: String,
    default: '',
  },
  networkValue: {
    type: String,
    default: '',
  },
  stats: {
    type: Array,
    required: true,
  },
})
</script>

<template>
  <header class="page-header">
    <div class="page-copy">
      <UiBadge variant="secondary">{{ eyebrow }}</UiBadge>
      <h1>{{ title }}</h1>
      <p class="page-lead">{{ lead }}</p>
    </div>
    <UiCard class="hero-strip">
      <div class="hero-strip-copy">
        <div class="hero-strip-head">
          <p class="section-label">{{ heroLabel }}</p>
          <UiBadge v-if="statusLabel" :variant="statusVariant">{{ statusLabel }}</UiBadge>
        </div>
        <h2>{{ heroTitle }}</h2>
        <p v-if="heroDescription">{{ heroDescription }}</p>
        <div v-if="networkLabel || networkValue" class="hero-network-path">
          <span>{{ networkLabel }}</span>
          <strong>{{ networkValue }}</strong>
        </div>
      </div>
      <div class="hero-strip-stats">
        <div v-for="item in stats" :key="item.label" class="hero-stat">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.hint }}</small>
        </div>
      </div>
    </UiCard>
  </header>
</template>

<style scoped>
.page-header {
  min-height: 0;
}

.page-header > .hero-strip {
  min-height: 0;
}

.page-copy {
  min-height: 116px;
}

.hero-strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(18rem, 0.8fr);
  gap: 1rem;
  margin-top: 0.5rem;
  align-items: start;
}

.hero-strip-copy,
.hero-strip-stats {
  display: grid;
  gap: 0.75rem;
  min-width: 0;
}

.hero-strip-head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}

.hero-strip-copy h2 {
  font-size: clamp(1.5rem, 3vw, 2.2rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.hero-strip-copy p:last-child {
  color: var(--muted-foreground);
  line-height: 1.6;
}

.hero-network-path {
  display: grid;
  gap: 0.35rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card-muted);
}

.hero-network-path span {
  color: var(--muted-foreground);
  font-size: 0.78rem;
  font-weight: 700;
}

.hero-network-path strong {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.95rem;
  line-height: 1.45;
}

.hero-strip-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.hero-stat {
  display: grid;
  gap: 0.4rem;
  padding: 1rem 1.05rem;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card-muted);
}

.hero-stat strong {
  font-size: 1.2rem;
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.hero-stat small {
  color: var(--muted-foreground);
  line-height: 1.55;
}

@media (max-width: 980px) {
  .page-header {
    display: grid;
    gap: 0.85rem;
  }

  .page-copy {
    min-height: 0;
    padding-top: 0;
  }

  .page-copy h1 {
    margin-top: 0.65rem;
    font-size: clamp(2rem, 10vw, 2.85rem);
  }

  .page-lead {
    font-size: 0.95rem;
  }

  .hero-strip {
    grid-template-columns: 1fr;
    margin-top: 0;
    padding: 1rem;
  }

  .hero-strip-stats,
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .hero-stat {
    padding: 0.85rem;
  }
}

@media (max-width: 560px) {
  .hero-strip-stats {
    grid-template-columns: 1fr;
  }

  .hero-network-path strong {
    white-space: normal;
    word-break: break-all;
  }
}
</style>
