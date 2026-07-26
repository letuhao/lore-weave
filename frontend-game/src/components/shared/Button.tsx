// Vendored shadcn-style Button. Session D may swap to actual shadcn
// vendoring; this minimal one keeps the scaffold compile-clean.

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { JSX } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  primary: 'bg-indigo-600 hover:bg-indigo-500 text-white',
  secondary: 'bg-slate-700 hover:bg-slate-600 text-slate-100',
  ghost: 'bg-transparent hover:bg-slate-800 text-slate-200',
};

export function Button({ variant = 'primary', children, className = '', ...rest }: ButtonProps): JSX.Element {
  return (
    <button
      type="button"
      className={`px-4 py-2 rounded font-semibold ${variantClass[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
