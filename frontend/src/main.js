// 这个入口文件负责挂载 Vue 应用，并加载全局样式和主页面组件。
import { createApp } from "vue";
import App from "./App.vue";
import "./styles.css";

createApp(App).mount("#app");
