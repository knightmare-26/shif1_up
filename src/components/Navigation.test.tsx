import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Navigation from './Navigation';

jest.mock('../config/features', () => ({ useLiveTiming: () => ({ enabled: false, loading: false }) }));

let location = '';
const LocationProbe = () => { location = useLocation().pathname; return null; };

/** A computer (the 1024px query matches) or a phone; motion stays on. */
function screenIs(desktop: boolean) {
  window.matchMedia = jest.fn().mockImplementation((query: string) => ({
    matches: desktop && query.includes('min-width: 1024px'),
    media: query, addEventListener: jest.fn(), removeEventListener: jest.fn(),
    addListener: jest.fn(), removeListener: jest.fn(), onchange: null, dispatchEvent: jest.fn(),
  }));
}

async function renderAt(path = '/dashboard') {
  await act(async () => {
    render(<MemoryRouter initialEntries={[path]}><Navigation /><LocationProbe /></MemoryRouter>);
  });
}

beforeEach(() => window.localStorage.clear());

test('on a computer the menu rolls out in the bar and stays out until the button is pressed again', async () => {
  screenIs(true);
  await renderAt();
  expect(screen.queryByRole('navigation', { name: 'Site' })).not.toBeInTheDocument();

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open menu' })); });
  const links = screen.getByRole('navigation', { name: 'Site' });
  expect(within(links).getAllByRole('link').map((a) => a.textContent))
    .toEqual(['Home', 'Dashboard', 'Predictions', 'LiveSoon', 'Data Manager']);
  expect(within(links).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();             // not the side panel

  // Moving to another page doesn't put it away.
  await act(async () => { fireEvent.click(within(links).getByRole('link', { name: 'Predictions' })); });
  expect(location).toBe('/predictions');
  expect(screen.getByRole('navigation', { name: 'Site' })).toBeInTheDocument();
  expect(window.localStorage.getItem('shif1:menu-rolled-out')).toBe('1');

  const button = screen.getByRole('button', { name: 'Close menu' });
  expect(button).toHaveAttribute('aria-expanded', 'true');
  await act(async () => { fireEvent.click(button); });
  await waitFor(() => expect(screen.queryByRole('navigation', { name: 'Site' })).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Open menu' })).toHaveAttribute('aria-expanded', 'false');
  expect(window.localStorage.getItem('shif1:menu-rolled-out')).toBe('0');
});

test('a menu left out is still out after a reload', async () => {
  screenIs(true);
  window.localStorage.setItem('shif1:menu-rolled-out', '1');
  await renderAt();

  expect(screen.getByRole('navigation', { name: 'Site' })).toBeInTheDocument();
});

test('on a phone the button opens the side panel as before, which closes on moving page', async () => {
  screenIs(false);
  window.localStorage.setItem('shif1:menu-rolled-out', '1');       // a computer's choice doesn't apply here
  await renderAt();
  expect(screen.queryByRole('navigation', { name: 'Site' })).not.toBeInTheDocument();

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open menu' })); });
  const panel = document.getElementById('site-menu') as HTMLElement;
  expect(panel).toBeInTheDocument();

  await act(async () => { fireEvent.click(within(panel).getByRole('link', { name: 'Predictions' })); });
  expect(location).toBe('/predictions');
  await waitFor(() => expect(document.getElementById('site-menu')).not.toBeInTheDocument());
});
