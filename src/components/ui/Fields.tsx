import React, { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, RefreshCw } from 'lucide-react';

const controlBase =
  'w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2 text-sm text-white transition-colors ' +
  'focus:border-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/40 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';

/** Label above a native select. Pass <option>s as children. */
export const SelectField: React.FC<{
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}> = ({ label, value, onChange, children, disabled, className = 'min-w-[140px]' }) => (
  <label className={`flex flex-col gap-1 ${className}`}>
    <span className="text-xs uppercase tracking-wide text-gray-400">{label}</span>
    <span className="relative block">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={`${controlBase} appearance-none pr-9`}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
        aria-hidden="true"
      />
    </span>
  </label>
);

export const TextField: React.FC<{
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}> = ({ label, value, onChange, placeholder, disabled, className = 'min-w-[200px]' }) => (
  <label className={`flex flex-col gap-1 ${className}`}>
    <span className="text-xs uppercase tracking-wide text-gray-400">{label}</span>
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={controlBase}
    />
  </label>
);

export const CheckboxField: React.FC<{
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}> = ({ label, checked, onChange, className = '' }) => (
  <label className={`flex items-center gap-2 self-end pb-2 text-sm text-gray-300 ${className}`}>
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="h-4 w-4 rounded border-gray-700 bg-gray-900 text-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/40"
    />
    {label}
  </label>
);

export interface CheckboxMenuOption {
  id: string;
  label: string;
}

/** A button that opens a list of checkboxes, e.g. to pick optional table columns. Closes on an
 *  outside click or Escape (which returns focus to the button). */
export const CheckboxMenu: React.FC<{
  label: string;
  options: CheckboxMenuOption[];
  selected: string[];
  onChange: (selected: string[]) => void;
  icon?: React.ReactNode;
  align?: 'left' | 'right';
}> = ({ label, options, selected, onChange, icon, align = 'right' }) => {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    root.current?.querySelector<HTMLInputElement>('input')?.focus();
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = (id: string, on: boolean) =>
    // Keep the options' order, whatever order they were ticked in.
    onChange(options.map((o) => o.id).filter((o) => (o === id ? on : selected.includes(o))));

  return (
    <div ref={root} className="relative">
      <button
        ref={button}
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 transition-colors hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60"
      >
        {icon}
        {label}
        {selected.length > 0 && (
          <span className="rounded bg-racing-red px-1.5 text-xs font-semibold text-white">{selected.length}</span>
        )}
        <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={menuId}
          role="group"
          aria-label={label}
          className={`absolute z-20 mt-2 min-w-[12rem] rounded-lg border border-gray-700 bg-gray-900 p-1 shadow-xl ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          {options.map((o) => (
            <label
              key={o.id}
              className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-gray-200 hover:bg-gray-800"
            >
              <input
                type="checkbox"
                checked={selected.includes(o.id)}
                onChange={(e) => toggle(o.id, e.target.checked)}
                className="h-4 w-4 rounded border-gray-700 bg-gray-900 text-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/40"
              />
              {o.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
};

export const FilterBar: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <div className={`mb-6 flex flex-wrap items-end gap-4 ${className}`}>{children}</div>;

export const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: 'primary' | 'secondary' | 'danger';
    loading?: boolean;
    icon?: React.ReactNode;
  }
> = ({ variant = 'primary', loading, icon, children, className = '', disabled, ...rest }) => {
  const styles = {
    primary: 'bg-racing-red text-white hover:bg-red-700',
    secondary: 'border border-gray-700 bg-gray-800 text-gray-200 hover:bg-gray-700',
    danger: 'bg-red-600 text-white hover:bg-red-700',
  }[variant];
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60 disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      {...rest}
    >
      {loading ? <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  );
};
