import { defineStore } from "pinia";
import { api } from "@/services/api";
import type { User } from "@/types";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    initialized: false,
    loading: false,
    user: null as User | null,
  }),
  getters: {
    authenticated: (state) => !!state.user,
    isAdmin: (state) => !!state.user?.is_admin,
  },
  actions: {
    async init() {
      if (this.initialized) return;
      this.loading = true;
      try {
        const data = await api.me();
        this.user = data.authenticated ? data.user : null;
      } finally {
        this.initialized = true;
        this.loading = false;
      }
    },
    async login(username: string, password: string) {
      const data = await api.login(username, password);
      this.user = data.user;
      this.initialized = true;
    },
    async register(username: string, password: string, confirm: string) {
      const data = await api.register(username, password, confirm);
      this.user = data.user;
      this.initialized = true;
    },
    async changePassword(oldPassword: string, newPassword: string, confirm: string) {
      await api.changePassword(oldPassword, newPassword, confirm);
    },
    async logout() {
      await api.logout();
      this.user = null;
      this.initialized = true;
    },
  },
});
