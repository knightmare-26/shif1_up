import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ChampionshipOutlook, DriverStanding } from '../../services/backendApi';
import { formatChance } from '../../utils/probability';
import { teamColor } from '../ui';

/** "Andrea Kimi Antonelli" -> ["Andrea Kimi", "Antonelli"]: the surname is set in capitals. */
export const splitName = (full: string): [string, string] => {
  const parts = (full || '').trim().split(/\s+/);
  return parts.length > 1 ? [parts.slice(0, -1).join(' '), parts[parts.length - 1]] : ['', parts[0] ?? ''];
};

const Spec: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <p className="text-lg uppercase text-white sm:text-xl">
    <span className="text-muted">{label}: </span>{value}
  </p>
);

/**
 * The title fight as profile cards: the top drivers one at a time — a panel in their team's colour
 * with the code in outline type, then a red tag (P1 | LEADER), the name with the surname in
 * capitals, and the numbers. Arrows, dots or the arrow keys move between them.
 */
export const ContendersCarousel: React.FC<{ drivers: DriverStanding[]; outlook?: ChampionshipOutlook | null }> = ({
  drivers, outlook,
}) => {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const field = drivers.slice(0, 5);
  if (!field.length) return null;
  const at = Math.min(index, field.length - 1);
  const driver = field[at];
  const leader = field[0];
  const [first, last] = splitName(driver.driver_name);
  const code = (driver.code || last.slice(0, 3)).toUpperCase();
  const colour = teamColor(driver.constructor);
  const row = outlook?.standings.find((r) => (r.code ?? '').toUpperCase() === code || r.name === driver.driver_name);
  const roundsLeft = outlook ? Math.max(0, outlook.rounds_total - outlook.rounds_completed) : null;
  const gap = Math.round((leader.points - driver.points) * 10) / 10;
  const tag = at === 0 ? 'Leader' : `${gap} pts behind`;
  const go = (step: number) => setIndex((at + step + field.length) % field.length);

  return (
    <section aria-roledescription="carousel" aria-label="The title fight"
      onKeyDown={(e) => { if (e.key === 'ArrowRight') go(1); if (e.key === 'ArrowLeft') go(-1); }}
      className="relative mx-auto max-w-[1600px] px-4 sm:px-6 lg:px-10">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14">
        <AnimatePresence mode="wait">
          <motion.div key={`visual-${code}`}
            initial={reduce ? false : { opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 30 }}
            transition={{ duration: 0.35 }}
            className="relative aspect-[4/3] overflow-hidden lg:aspect-auto lg:min-h-[440px]"
            style={{ background: `linear-gradient(135deg, ${colour} 0%, ${colour}33 45%, #050505 85%)` }}>
            <div className="absolute inset-0 opacity-[0.07]"
              style={{ backgroundImage: 'repeating-linear-gradient(115deg, #fff 0 2px, transparent 2px 22px)' }} />
            <span aria-hidden="true" className="display absolute -bottom-[0.12em] -left-[0.04em] select-none text-[clamp(7rem,19vw,17rem)] text-transparent"
              style={{ WebkitTextStroke: '2px rgba(255,255,255,0.75)' }}>
              {code}
            </span>
            {driver.number != null && (
              <span aria-hidden="true" className="display absolute right-6 top-5 text-6xl text-white/90">#{driver.number}</span>
            )}
          </motion.div>
        </AnimatePresence>

        <AnimatePresence mode="wait">
          <motion.div key={`text-${code}`} aria-live="polite"
            initial={reduce ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3, delay: reduce ? 0 : 0.08 }}
            className="flex flex-col justify-center">
            <p className="label">
              <span className="text-racing-red">P{driver.position}</span>
              <span className="mx-2 text-white">|</span>
              <span className="text-white">{tag}</span>
            </p>
            <h3 className="display mt-3 text-[clamp(2.75rem,6vw,5.5rem)]">
              {first && <span className="font-light text-white">{first} </span>}
              <span className="uppercase text-white">{last}</span>
            </h3>
            <p className="label mt-3 text-muted">{driver.nationality}</p>
            <div className="mt-8 space-y-1.5">
              <Spec label="Team" value={driver.constructor} />
              <Spec label="Points" value={driver.points} />
              <Spec label="Wins" value={driver.wins} />
              {row && outlook?.status !== 'finished' && (
                <Spec label="Title chance" value={<span className="text-racing-red">{formatChance(row.title_probability)}</span>} />
              )}
            </div>
            <p className="mt-6 max-w-xl leading-relaxed text-gray-300">
              {at === 0
                ? `Leads the championship${field[1] ? ` by ${Math.round((driver.points - field[1].points) * 10) / 10} points` : ''}${roundsLeft ? ` with ${roundsLeft} round${roundsLeft === 1 ? '' : 's'} to go` : ''}.`
                : `${gap} points behind ${splitName(leader.driver_name)[1]}${roundsLeft ? `, ${roundsLeft} round${roundsLeft === 1 ? '' : 's'} left` : ''}${row && !row.alive ? ' — out of the title fight' : ''}.`}
            </p>
            <Link to="/predictions?tab=title"
              className="label mt-8 inline-flex w-fit items-center gap-1 text-white transition-colors hover:text-racing-red focus:outline-none focus-visible:text-racing-red">
              View the title race <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="mt-10 flex items-center justify-between">
        <div className="flex gap-2" role="group" aria-label="Choose a driver">
          {field.map((d, i) => (
            <button key={d.driver_id} type="button" onClick={() => setIndex(i)}
              aria-label={`${d.driver_name}, P${d.position}`} aria-current={i === at ? 'true' : undefined}
              className={`h-2.5 w-7 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/70 ${
                i === at ? 'bg-white' : 'bg-white/20 hover:bg-white/50'}`} />
          ))}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => go(-1)} aria-label="Previous driver"
            className="border border-white/40 p-2.5 text-white transition-colors hover:border-white hover:bg-white hover:text-black focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/70">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button type="button" onClick={() => go(1)} aria-label="Next driver"
            className="border border-white/40 p-2.5 text-white transition-colors hover:border-white hover:bg-white hover:text-black focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/70">
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </section>
  );
};
