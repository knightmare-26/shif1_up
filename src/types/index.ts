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
  preferences: UserPreferences;
  createdAt: Date;
  is_admin?: boolean;
}

export interface UserDisplay {
  id: string;
  username: string;
  preferences: UserPreferences;
  createdAt: Date;
}
