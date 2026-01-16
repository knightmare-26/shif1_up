export interface UserPreferences {
  favoriteDriver: string;
  favoriteTrack: string;
  favoriteTeam: string;
  experienceLevel: 'beginner' | 'intermediate' | 'expert';
  notifications: boolean;
}

export interface User {
  id: string;
  username: string;
  email: string;
  password: string; // Hashed password
  preferences: UserPreferences;
  createdAt: Date;
}

export interface UserDisplay {
  id: string;
  username: string;
  preferences: UserPreferences;
  createdAt: Date;
}
