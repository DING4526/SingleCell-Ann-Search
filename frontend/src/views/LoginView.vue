<template>
  <div class="login-page">
    <div class="login-panel">
      <div class="brand login-brand">
        <div class="brand-mark">SC</div>
        <div>
          <div class="brand-title">ANN Research</div>
          <div class="brand-subtitle">Professional single-cell retrieval workspace</div>
        </div>
      </div>
      <a-tabs v-model:active-key="mode">
        <a-tab-pane key="login" tab="登录">
          <a-form :model="loginForm" layout="vertical" @finish="submitLogin">
            <a-form-item label="用户名" name="username" :rules="[{ required: true, message: '请输入用户名' }]">
              <a-input v-model:value="loginForm.username" autocomplete="username" />
            </a-form-item>
            <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
              <a-input-password v-model:value="loginForm.password" autocomplete="current-password" />
            </a-form-item>
            <a-button type="primary" html-type="submit" block :loading="loading">进入平台</a-button>
          </a-form>
        </a-tab-pane>
        <a-tab-pane key="register" tab="注册">
          <a-form :model="registerForm" layout="vertical" @finish="submitRegister">
            <a-form-item label="用户名" name="username" :rules="[{ required: true, message: '请输入用户名' }]">
              <a-input v-model:value="registerForm.username" autocomplete="username" />
            </a-form-item>
            <a-form-item label="密码" name="password" :rules="[{ required: true, min: 4, message: '密码至少 4 位' }]">
              <a-input-password v-model:value="registerForm.password" autocomplete="new-password" />
            </a-form-item>
            <a-form-item label="确认密码" name="confirm" :rules="[{ required: true, message: '请再次输入密码' }]">
              <a-input-password v-model:value="registerForm.confirm" autocomplete="new-password" />
            </a-form-item>
            <a-button type="primary" html-type="submit" block :loading="loading">创建账号</a-button>
          </a-form>
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const mode = ref("login");
const loading = ref(false);
const loginForm = reactive({ username: "", password: "" });
const registerForm = reactive({ username: "", password: "", confirm: "" });

async function submitLogin() {
  loading.value = true;
  try {
    await auth.login(loginForm.username, loginForm.password);
    router.push(String(route.query.next || "/overview"));
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}

async function submitRegister() {
  loading.value = true;
  try {
    await auth.register(registerForm.username, registerForm.password, registerForm.confirm);
    router.push("/overview");
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #f6f8fb;
  padding: 24px;
}

.login-panel {
  width: min(420px, 100%);
  background: #ffffff;
  border: 1px solid #e5eaf2;
  border-radius: 8px;
  padding: 22px;
}

.login-brand {
  padding: 0 0 18px;
  border-bottom: 0;
}
</style>
