import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import bcrypt from 'bcryptjs';
import { User, UserDisplay, UserPreferences } from '../types';
import { databaseService, DatabaseUser } from '../services/database';

interface AuthContextType {
  isAuthenticated: boolean;
  user: User | null;
  login: (username: string, password: string) => Promise<boolean>;
  signup: (userData: {
    username: string;
    email: string;
    password: string;
    preferences: UserPreferences;
  }) => Promise<boolean>;
  logout: () => void;
  updatePreferences: (preferences: Partial<UserPreferences>) => void;
  getPublicUserData: () => UserDisplay | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);

  // Load user data from database on app start
  useEffect(() => {
    const loadUserFromStorage = async () => {
      try {
        const savedUser = localStorage.getItem('shif1_user');
        const savedAuth = localStorage.getItem('shif1_auth');
        
        if (savedUser && savedAuth === 'true') {
          const userData = JSON.parse(savedUser);
          // Verify user still exists in database
          const dbUser = await databaseService.getUserByUsername(userData.username);
          if (dbUser) {
            setUser(dbUser);
            setIsAuthenticated(true);
          } else {
            // User no longer exists in database, clear storage
            localStorage.removeItem('shif1_user');
            localStorage.removeItem('shif1_auth');
          }
        }
      } catch (error) {
        console.error('Error loading user data:', error);
        localStorage.removeItem('shif1_user');
        localStorage.removeItem('shif1_auth');
      }
    };

    loadUserFromStorage();
  }, []);

  const saveUserToStorage = (userData: User) => {
    localStorage.setItem('shif1_user', JSON.stringify(userData));
    localStorage.setItem('shif1_auth', 'true');
  };

  const clearUserFromStorage = () => {
    localStorage.removeItem('shif1_user');
    localStorage.removeItem('shif1_auth');
  };

  const hashPassword = async (password: string): Promise<string> => {
    const saltRounds = 12;
    return await bcrypt.hash(password, saltRounds);
  };

  const verifyPassword = async (password: string, hashedPassword: string): Promise<boolean> => {
    return await bcrypt.compare(password, hashedPassword);
  };

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      // Get user from database
      const dbUser = await databaseService.getUserByUsername(username);
      
      if (dbUser) {
        // Verify password hash
        const isValidPassword = await verifyPassword(password, dbUser.password);
        if (isValidPassword) {
          setUser(dbUser);
          setIsAuthenticated(true);
          saveUserToStorage(dbUser);
          return true;
        }
      }
      
      return false;
    } catch (error) {
      console.error('Login error:', error);
      return false;
    }
  };

  const signup = async (userData: {
    username: string;
    email: string;
    password: string;
    preferences: UserPreferences;
  }): Promise<boolean> => {
    try {
      // Hash the password
      const hashedPassword = await hashPassword(userData.password);

      // Create new user
      const newUser: DatabaseUser = {
        id: Date.now().toString(),
        username: userData.username,
        email: userData.email,
        password: hashedPassword,
        preferences: userData.preferences,
        createdAt: new Date(),
      };

      // Save to database
      const success = await databaseService.createUser(newUser);
      
      if (success) {
        setUser(newUser);
        setIsAuthenticated(true);
        saveUserToStorage(newUser);
        return true;
      } else {
        return false; // User already exists
      }
    } catch (error) {
      console.error('Signup error:', error);
      return false;
    }
  };

  const logout = () => {
    setIsAuthenticated(false);
    setUser(null);
    clearUserFromStorage();
  };

  const updatePreferences = async (newPreferences: Partial<UserPreferences>) => {
    if (user) {
      const updatedUser = {
        ...user,
        preferences: {
          ...user.preferences,
          ...newPreferences,
        },
      };
      
      // Update in database
      try {
        await databaseService.updateUser(updatedUser);
        setUser(updatedUser);
        saveUserToStorage(updatedUser);
      } catch (error) {
        console.error('Error updating preferences:', error);
      }
    }
  };

  const getPublicUserData = (): UserDisplay | null => {
    if (!user) return null;
    
    return {
      id: user.id,
      username: user.username,
      preferences: user.preferences,
      createdAt: user.createdAt,
    };
  };

  const value: AuthContextType = {
    isAuthenticated,
    user,
    login,
    signup,
    logout,
    updatePreferences,
    getPublicUserData,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
