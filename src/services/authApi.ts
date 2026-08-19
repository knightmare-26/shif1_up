/**
 * Backend Auth API — calls /auth/* endpoints on the FastAPI server.
 * JWT is stored in localStorage (trade-off: simpler than httpOnly cookies
 * but susceptible to XSS; acceptable for this project's threat model).
 */

import { UserPreferences } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const TOKEN_KEY = 'shif1_token';

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  preferences: UserPreferences;
  is_admin?: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export async function authSignup(data: {
  username: string;
  email: string;
  password: string;
}): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Signup failed');
  }
  return res.json();
}

export async function authLogin(username: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Invalid username or password');
  }
  return res.json();
}

export async function authGetMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Token invalid or expired');
  return res.json();
}

export async function authUpdatePreferences(
  token: string,
  preferences: UserPreferences
): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/me/preferences`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(preferences),
  });
}
