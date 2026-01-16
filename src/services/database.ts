interface DatabaseUser {
  id: string;
  username: string;
  email: string;
  password: string;
  preferences: {
    favoriteDriver: string;
    favoriteTrack: string;
    favoriteTeam: string;
    experienceLevel: 'beginner' | 'intermediate' | 'expert';
    notifications: boolean;
  };
  createdAt: Date;
}

class DatabaseService {
  private dbName = 'Shif1UpDB';
  private dbVersion = 1;
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        
        // Create users store
        if (!db.objectStoreNames.contains('users')) {
          const userStore = db.createObjectStore('users', { keyPath: 'id' });
          userStore.createIndex('username', 'username', { unique: true });
          userStore.createIndex('email', 'email', { unique: true });
        }
      };
    });
  }

  async createUser(user: DatabaseUser): Promise<boolean> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['users'], 'readwrite');
      const store = transaction.objectStore('users');
      
      const request = store.add(user);
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => {
        if (request.error?.name === 'ConstraintError') {
          resolve(false); // User already exists
        } else {
          reject(request.error);
        }
      };
    });
  }

  async getUserByUsername(username: string): Promise<DatabaseUser | null> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['users'], 'readonly');
      const store = transaction.objectStore('users');
      const index = store.index('username');
      
      const request = index.get(username);
      
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async updateUser(user: DatabaseUser): Promise<boolean> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['users'], 'readwrite');
      const store = transaction.objectStore('users');
      
      const request = store.put(user);
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  }

  async deleteUser(id: string): Promise<boolean> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['users'], 'readwrite');
      const store = transaction.objectStore('users');
      
      const request = store.delete(id);
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  }

  async getAllUsers(): Promise<DatabaseUser[]> {
    if (!this.db) await this.init();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['users'], 'readonly');
      const store = transaction.objectStore('users');
      
      const request = store.getAll();
      
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}

export const databaseService = new DatabaseService();
export type { DatabaseUser };
