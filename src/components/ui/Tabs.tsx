import React from 'react';

export interface TabItem<T extends string> {
  id: T;
  label: string;
  icon?: React.ReactNode;
}

/** Underline tabs with the full ARIA tab pattern (arrow keys, Home/End). */
export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
  idPrefix = 'tabs',
}: {
  tabs: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  label: string;
  idPrefix?: string;
}) {
  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    let next = -1;
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(tabs[next].id);
    document.getElementById(`${idPrefix}-tab-${tabs[next].id}`)?.focus();
  };

  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-gray-800">
      {tabs.map((t, i) => {
        const selected = t.id === active;
        return (
          <button
            key={t.id}
            id={`${idPrefix}-tab-${t.id}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${t.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`-mb-px flex items-center gap-2 whitespace-nowrap rounded-t border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60 ${
              selected
                ? 'border-racing-red text-white'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.icon && <span aria-hidden="true">{t.icon}</span>}
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export const TabPanel: React.FC<{
  id: string;
  idPrefix?: string;
  children: React.ReactNode;
  className?: string;
}> = ({ id, idPrefix = 'tabs', children, className }) => (
  <div
    role="tabpanel"
    id={`${idPrefix}-panel-${id}`}
    aria-labelledby={`${idPrefix}-tab-${id}`}
    className={className}
  >
    {children}
  </div>
);
