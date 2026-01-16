import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Radio, 
  Activity, 
  Clock, 
  MapPin, 
  Users, 
  TrendingUp,
  AlertCircle,
  CheckCircle,
  RefreshCw,
  Play,
  Pause,
  Square
} from 'lucide-react';
import { backendApi, LiveSession as BackendLiveSession, LivePosition as BackendLivePosition } from '../services/backendApi';

interface LiveSession {
  year: number;
  round: number;
  session: string;
  status: 'Live' | 'Finished' | 'Scheduled' | 'Cancelled';
  lastUpdate: string;
}

interface LivePosition {
  position: number;
  driverNumber: number;
  driverName: string;
  teamName: string;
  time: string;
  gap: string;
  interval: string;
  laps: number;
  status: string;
}

interface LiveTiming {
  driverNumber: number;
  driverName: string;
  teamName: string;
  sector1: string;
  sector2: string;
  sector3: string;
  lapTime: string;
  bestLap: string;
  lastLap: string;
  position: number;
}

const LiveDataMonitor: React.FC = () => {
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [currentSession, setCurrentSession] = useState<LiveSession | null>(null);
  const [livePositions, setLivePositions] = useState<LivePosition[]>([]);
  const [liveTiming, setLiveTiming] = useState<LiveTiming[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'error'>('disconnected');
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [selectedRound, setSelectedRound] = useState(1);
  const [selectedSession, setSelectedSession] = useState('R');
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // Mock live data for demonstration
  const mockLivePositions: LivePosition[] = [
    { position: 1, driverNumber: 1, driverName: 'VER', teamName: 'Red Bull Racing', time: '1:23:45.123', gap: 'Leader', interval: '', laps: 45, status: 'Running' },
    { position: 2, driverNumber: 16, driverName: 'LEC', teamName: 'Ferrari', time: '1:23:47.456', gap: '+2.333', interval: '+2.333', laps: 45, status: 'Running' },
    { position: 3, driverNumber: 44, driverName: 'HAM', teamName: 'Mercedes', time: '1:23:49.789', gap: '+4.666', interval: '+2.333', laps: 45, status: 'Running' },
    { position: 4, driverNumber: 4, driverName: 'NOR', teamName: 'McLaren', time: '1:23:52.012', gap: '+6.889', interval: '+2.223', laps: 45, status: 'Running' },
    { position: 5, driverNumber: 11, driverName: 'PER', teamName: 'Red Bull Racing', time: '1:23:54.345', gap: '+9.222', interval: '+2.333', laps: 45, status: 'Running' }
  ];

  const mockLiveTiming: LiveTiming[] = [
    { driverNumber: 1, driverName: 'VER', teamName: 'Red Bull Racing', sector1: '23.456', sector2: '45.789', sector3: '14.878', lapTime: '1:24.123', bestLap: '1:23.456', lastLap: '1:24.123', position: 1 },
    { driverNumber: 16, driverName: 'LEC', teamName: 'Ferrari', sector1: '23.567', sector2: '45.890', sector3: '14.999', lapTime: '1:24.456', bestLap: '1:23.789', lastLap: '1:24.456', position: 2 },
    { driverNumber: 44, driverName: 'HAM', teamName: 'Mercedes', sector1: '23.678', sector2: '45.901', sector3: '15.000', lapTime: '1:24.579', bestLap: '1:24.012', lastLap: '1:24.579', position: 3 }
  ];

  useEffect(() => {
    if (isMonitoring) {
      startLiveMonitoring();
    } else {
      stopLiveMonitoring();
    }

    return () => {
      stopLiveMonitoring();
    };
  }, [isMonitoring, selectedYear, selectedRound, selectedSession]);

  const startLiveMonitoring = () => {
    setConnectionStatus('connected');
    setCurrentSession({
      year: selectedYear,
      round: selectedRound,
      session: selectedSession,
      status: 'Live',
      lastUpdate: new Date().toISOString()
    });

    // Simulate live data updates every 5 seconds
    intervalRef.current = setInterval(async () => {
      try {
        // In real implementation, this would fetch from FastF1 live data
        // const liveData = await backendApi.getLiveSessionData();
        
        // Update mock data with slight variations
        setLivePositions(prev => 
          prev.map((pos, index) => ({
            ...pos,
            time: generateMockTime(),
            gap: index === 0 ? 'Leader' : `+${(Math.random() * 10).toFixed(3)}`,
            interval: index === 0 ? '' : `+${(Math.random() * 5).toFixed(3)}`,
            laps: pos.laps + (Math.random() > 0.7 ? 1 : 0)
          }))
        );

        setLiveTiming(prev => 
          prev.map(timing => ({
            ...timing,
            sector1: generateMockSectorTime(),
            sector2: generateMockSectorTime(),
            sector3: generateMockSectorTime(),
            lapTime: generateMockLapTime(),
            lastLap: generateMockLapTime()
          }))
        );

        setLastUpdate(new Date());
        setConnectionStatus('connected');
      } catch (error) {
        console.error('Error fetching live data:', error);
        setConnectionStatus('error');
      }
    }, 5000);

    // Initialize with mock data
    setLivePositions(mockLivePositions);
    setLiveTiming(mockLiveTiming);
    setLastUpdate(new Date());
  };

  const stopLiveMonitoring = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setConnectionStatus('disconnected');
  };

  const generateMockTime = () => {
    const minutes = Math.floor(Math.random() * 2) + 1;
    const seconds = Math.floor(Math.random() * 60);
    const milliseconds = Math.floor(Math.random() * 1000);
    return `${minutes}:${seconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
  };

  const generateMockSectorTime = () => {
    const seconds = Math.floor(Math.random() * 30) + 20;
    const milliseconds = Math.floor(Math.random() * 1000);
    return `${seconds}.${milliseconds.toString().padStart(3, '0')}`;
  };

  const generateMockLapTime = () => {
    const minutes = 1;
    const seconds = Math.floor(Math.random() * 30) + 20;
    const milliseconds = Math.floor(Math.random() * 1000);
    return `${minutes}:${seconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return 'text-green-500';
      case 'error':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircle className="w-4 h-4" />;
      case 'error':
        return <AlertCircle className="w-4 h-4" />;
      default:
        return <Radio className="w-4 h-4" />;
    }
  };

  return (
    <div className="min-h-screen bg-carbon-black text-pure-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-racing text-racing-red mb-4">
            Live F1 Data Monitor
          </h1>
          <p className="text-gray-300 text-lg">
            Real-time telemetry and timing data during F1 sessions
          </p>
        </motion.div>

        {/* Control Panel */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-track-grey rounded-lg p-6 mb-8"
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <span className="text-carbon-black font-medium">Year:</span>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                  className="px-3 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-racing-red"
                  disabled={isMonitoring}
                >
                  {Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - i).map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center space-x-2">
                <span className="text-carbon-black font-medium">Round:</span>
                <select
                  value={selectedRound}
                  onChange={(e) => setSelectedRound(parseInt(e.target.value))}
                  className="px-3 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-racing-red"
                  disabled={isMonitoring}
                >
                  {Array.from({ length: 24 }, (_, i) => i + 1).map(round => (
                    <option key={round} value={round}>{round}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center space-x-2">
                <span className="text-carbon-black font-medium">Session:</span>
                <select
                  value={selectedSession}
                  onChange={(e) => setSelectedSession(e.target.value)}
                  className="px-3 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-racing-red"
                  disabled={isMonitoring}
                >
                  <option value="FP1">Free Practice 1</option>
                  <option value="FP2">Free Practice 2</option>
                  <option value="FP3">Free Practice 3</option>
                  <option value="Q">Qualifying</option>
                  <option value="R">Race</option>
                </select>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className={`flex items-center space-x-2 ${getStatusColor(connectionStatus)}`}>
                {getStatusIcon(connectionStatus)}
                <span className="text-sm font-medium">
                  {connectionStatus.charAt(0).toUpperCase() + connectionStatus.slice(1)}
                </span>
              </div>

              {lastUpdate && (
                <div className="flex items-center space-x-2 text-gray-600">
                  <Clock className="w-4 h-4" />
                  <span className="text-sm">
                    Last update: {lastUpdate.toLocaleTimeString()}
                  </span>
                </div>
              )}

              <button
                onClick={() => setIsMonitoring(!isMonitoring)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors duration-300 flex items-center space-x-2 ${
                  isMonitoring
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-racing-red hover:bg-red-700 text-white'
                }`}
              >
                {isMonitoring ? (
                  <>
                    <Square className="w-4 h-4" />
                    Stop Monitoring
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Start Monitoring
                  </>
                )}
              </button>
            </div>
          </div>
        </motion.div>

        {/* Live Data Display */}
        <AnimatePresence>
          {isMonitoring && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="grid grid-cols-1 lg:grid-cols-2 gap-8"
            >
              {/* Live Positions */}
              <div className="bg-track-grey rounded-lg p-6">
                <h2 className="text-2xl font-bold text-carbon-black mb-4 flex items-center">
                  <Users className="w-6 h-6 mr-2 text-racing-red" />
                  Live Positions
                </h2>
                
                <div className="space-y-2">
                  {livePositions.map((position, index) => (
                    <motion.div
                      key={position.driverNumber}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                      className="bg-white rounded-lg p-4 flex items-center justify-between"
                    >
                      <div className="flex items-center space-x-4">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${
                          position.position <= 3 ? 'bg-racing-red' : 'bg-gray-500'
                        }`}>
                          {position.position}
                        </div>
                        <div>
                          <div className="font-bold text-carbon-black">
                            {position.driverName}
                          </div>
                          <div className="text-sm text-gray-600">
                            {position.teamName}
                          </div>
                        </div>
                      </div>
                      
                      <div className="text-right">
                        <div className="font-mono text-carbon-black">
                          {position.time}
                        </div>
                        <div className="text-sm text-gray-600">
                          {position.gap}
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* Live Timing */}
              <div className="bg-track-grey rounded-lg p-6">
                <h2 className="text-2xl font-bold text-carbon-black mb-4 flex items-center">
                  <Activity className="w-6 h-6 mr-2 text-racing-red" />
                  Live Timing
                </h2>
                
                <div className="space-y-2">
                  {liveTiming.map((timing, index) => (
                    <motion.div
                      key={timing.driverNumber}
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                      className="bg-white rounded-lg p-4"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="font-bold text-carbon-black">
                          {timing.driverName} - {timing.teamName}
                        </div>
                        <div className="text-sm text-gray-600">
                          P{timing.position}
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-4 gap-2 text-sm">
                        <div>
                          <div className="text-gray-600">S1</div>
                          <div className="font-mono text-carbon-black">{timing.sector1}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">S2</div>
                          <div className="font-mono text-carbon-black">{timing.sector2}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">S3</div>
                          <div className="font-mono text-carbon-black">{timing.sector3}</div>
                        </div>
                        <div>
                          <div className="text-gray-600">Lap</div>
                          <div className="font-mono text-carbon-black">{timing.lapTime}</div>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Session Info */}
        {currentSession && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mt-8 bg-track-grey rounded-lg p-6"
          >
            <h2 className="text-2xl font-bold text-carbon-black mb-4 flex items-center">
              <MapPin className="w-6 h-6 mr-2 text-racing-red" />
              Session Information
            </h2>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-carbon-black">
                  {currentSession.year}
                </div>
                <div className="text-sm text-gray-600">Year</div>
              </div>
              
              <div className="bg-white rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-carbon-black">
                  {currentSession.round}
                </div>
                <div className="text-sm text-gray-600">Round</div>
              </div>
              
              <div className="bg-white rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-carbon-black">
                  {currentSession.session}
                </div>
                <div className="text-sm text-gray-600">Session</div>
              </div>
              
              <div className="bg-white rounded-lg p-4 text-center">
                <div className={`text-2xl font-bold ${
                  currentSession.status === 'Live' ? 'text-green-600' : 'text-gray-600'
                }`}>
                  {currentSession.status}
                </div>
                <div className="text-sm text-gray-600">Status</div>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default LiveDataMonitor;
