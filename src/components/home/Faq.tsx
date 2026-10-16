import React, { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';

export interface FaqItem {
  q: string;
  a: React.ReactNode;
}

/** Questions in red-edged boxes; one opens at a time. Buttons with aria-expanded, answers as regions. */
export const Faq: React.FC<{ items: FaqItem[] }> = ({ items }) => {
  const [open, setOpen] = useState<number | null>(null);
  const base = useId();
  return (
    <div className="mx-auto max-w-3xl space-y-3">
      {items.map((item, i) => {
        const expanded = open === i;
        const panel = `${base}-a${i}`;
        return (
          <div key={item.q} className={`border bg-[#1a1a1a] transition-colors ${expanded ? 'border-racing-red' : 'border-racing-red/60'}`}>
            <h3>
              <button type="button" aria-expanded={expanded} aria-controls={panel}
                onClick={() => setOpen(expanded ? null : i)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-sm font-medium uppercase tracking-wider text-white focus:outline-none focus-visible:bg-white/5">
                {item.q}
                <ChevronDown className={`h-5 w-5 flex-shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`} aria-hidden="true" />
              </button>
            </h3>
            <div id={panel} role="region" hidden={!expanded} className="px-5 pb-5 leading-relaxed text-gray-300">
              {item.a}
            </div>
          </div>
        );
      })}
    </div>
  );
};
