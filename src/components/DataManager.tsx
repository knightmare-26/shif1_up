import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  Download, 
  Database, 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  Calendar,
  Users,
  MapPin,
  Trophy,
  BarChart3
} from 'lucide-react';
import { f1DataExtractor, DataExtractionStats } from '../services/f1DataExtractor';

const DataManager: React.FC = () => {
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionProgress, setExtractionProgress] = useState(0);
  const [extractionStats, setExtractionStats] = useState<DataExtractionStats | null>(null);
  const [dataSummary, setDataSummary] = useState(f1DataExtractor.getDataSummary());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Update data summary periodically
    const interval = setInterval(() => {
      setDataSummary(f1DataExtractor.getDataSummary());
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const startDataExtraction = async () => {
    setIsExtracting(true);
    setError(null);
    setExtractionProgress(0);

    try {
      console.log('🚀 Starting comprehensive F1 data extraction...');
      
      // Start extraction for years 2000 to current year
      const currentYear = new Date().getFullYear();
      const stats = await f1DataExtractor.extractAllData(2000, currentYear);
      
      setExtractionStats(stats);
      setDataSummary(f1DataExtractor.getDataSummary());
      setExtractionProgress(100);
      
      console.log('✅ Data extraction completed successfully!');
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to extract data';
      setError(errorMessage);
      console.error('❌ Data extraction failed:', err);
    } finally {
      setIsExtracting(false);
    }
  };

  const clearAllData = () => {
    f1DataExtractor.clearCache();
    setDataSummary(f1DataExtractor.getDataSummary());
    setExtractionStats(null);
    setError(null);
  };

  const getStatusColor = () => {
    if (error) return 'text-red-500';
    if (isExtracting) return 'text-yellow-500';
    if (dataSummary.totalYears > 0) return 'text-green-500';
    return 'text-gray-500';
  };

  const getStatusIcon = () => {
    if (error) return <AlertCircle className="w-5 h-5" />;
    if (isExtracting) return <RefreshCw className="w-5 h-5 animate-spin" />;
    if (dataSummary.totalYears > 0) return <CheckCircle className="w-5 h-5" />;
    return <Database className="w-5 h-5" />;
  };

  return (
    <div className="min-h-screen bg-carbon-black text-pure-white p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-racing text-racing-red mb-2">
            F1 Data Manager
          </h1>
          <p className="text-gray-400">
            Efficiently extract and manage F1 data across all years
          </p>
        </motion.div>

        {/* Status Overview */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8"
        >
          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              {getStatusIcon()}
              <h3 className="text-lg font-semibold text-pure-white">Status</h3>
            </div>
            <p className={`text-2xl font-bold ${getStatusColor()}`}>
              {error ? 'Error' : isExtracting ? 'Extracting...' : dataSummary.totalYears > 0 ? 'Ready' : 'No Data'}
            </p>
            <p className="text-sm text-gray-400">
              {dataSummary.lastUpdated ? `Updated ${dataSummary.lastUpdated.toLocaleString()}` : 'Never updated'}
            </p>
          </div>

          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              <Calendar className="w-6 h-6 text-racing-red" />
              <h3 className="text-lg font-semibold text-pure-white">Years</h3>
            </div>
            <p className="text-2xl font-bold text-pure-white">
              {dataSummary.totalYears}
            </p>
            <p className="text-sm text-gray-400">
              {dataSummary.years.length > 0 ? `${dataSummary.years[0]}-${dataSummary.years[dataSummary.years.length - 1]}` : 'No data'}
            </p>
          </div>

          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              <Users className="w-6 h-6 text-turbo-teal" />
              <h3 className="text-lg font-semibold text-pure-white">Drivers</h3>
            </div>
            <p className="text-2xl font-bold text-pure-white">
              {dataSummary.totalDrivers.toLocaleString()}
            </p>
            <p className="text-sm text-gray-400">
              Total driver records
            </p>
          </div>

          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              <Trophy className="w-6 h-6 text-pit-stop-yellow" />
              <h3 className="text-lg font-semibold text-pure-white">Races</h3>
            </div>
            <p className="text-2xl font-bold text-pure-white">
              {dataSummary.totalRaces.toLocaleString()}
            </p>
            <p className="text-sm text-gray-400">
              Total race records
            </p>
          </div>
        </motion.div>

        {/* Action Buttons */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="flex flex-wrap gap-4 mb-8"
        >
          <button
            onClick={startDataExtraction}
            disabled={isExtracting}
            className="bg-racing-red text-pure-white px-6 py-3 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            {isExtracting ? (
              <RefreshCw className="w-5 h-5 animate-spin" />
            ) : (
              <Download className="w-5 h-5" />
            )}
            <span>
              {isExtracting ? 'Extracting Data...' : 'Extract All Data'}
            </span>
          </button>

          <button
            onClick={clearAllData}
            disabled={isExtracting}
            className="bg-gray-700 text-pure-white px-6 py-3 rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            <Database className="w-5 h-5" />
            <span>Clear Cache</span>
          </button>
        </motion.div>

        {/* Progress Bar */}
        {isExtracting && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <h3 className="text-lg font-semibold text-pure-white mb-4">Extraction Progress</h3>
              <div className="w-full bg-gray-700 rounded-full h-3 mb-4">
                <motion.div
                  className="bg-racing-red h-3 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${extractionProgress}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
              <p className="text-sm text-gray-400">
                {extractionProgress}% complete
              </p>
            </div>
          </motion.div>
        )}

        {/* Error Display */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <div className="bg-red-900/20 border border-red-500 rounded-xl p-6">
              <div className="flex items-center space-x-3 mb-2">
                <AlertCircle className="w-6 h-6 text-red-500" />
                <h3 className="text-lg font-semibold text-red-500">Extraction Error</h3>
              </div>
              <p className="text-red-300">{error}</p>
            </div>
          </motion.div>
        )}

        {/* Extraction Results */}
        {extractionStats && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <h3 className="text-xl font-bold text-racing-red mb-4">Extraction Results</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="text-center">
                  <div className="text-3xl font-bold text-pure-white">{extractionStats.yearsProcessed}</div>
                  <div className="text-sm text-gray-400">Years Processed</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-turbo-teal">{extractionStats.totalDrivers.toLocaleString()}</div>
                  <div className="text-sm text-gray-400">Drivers</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-pit-stop-yellow">{extractionStats.totalTeams.toLocaleString()}</div>
                  <div className="text-sm text-gray-400">Teams</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-racing-red">{extractionStats.totalRaces.toLocaleString()}</div>
                  <div className="text-sm text-gray-400">Races</div>
                </div>
              </div>
              
              {extractionStats.errors.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-lg font-semibold text-yellow-500 mb-2">Warnings ({extractionStats.errors.length})</h4>
                  <div className="space-y-1">
                    {extractionStats.errors.slice(0, 5).map((error, index) => (
                      <p key={index} className="text-sm text-yellow-300">{error}</p>
                    ))}
                    {extractionStats.errors.length > 5 && (
                      <p className="text-sm text-gray-400">... and {extractionStats.errors.length - 5} more</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Available Years List */}
        {dataSummary.years.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-gray-900 rounded-xl p-6 shadow-2xl"
          >
            <h3 className="text-xl font-bold text-racing-red mb-4">Available Years</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {dataSummary.years.map(year => (
                <div
                  key={year}
                  className="bg-gray-800 rounded-lg p-3 text-center hover:bg-gray-700 transition-colors"
                >
                  <div className="text-lg font-bold text-pure-white">{year}</div>
                  <div className="text-xs text-gray-400">
                    {dataSummary.totalDrivers > 0 ? 'Ready' : 'Loading...'}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default DataManager;
