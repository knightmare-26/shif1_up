import React from 'react';
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
