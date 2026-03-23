import axios from 'axios'

const instance = axios.create({
  baseURL: '/api',
})

// Attach auth token to every request
instance.interceptors.request.use((config) => {
  const token = localStorage.getItem('sb_token')
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// On 401, clear token and redirect to login
instance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('sb_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const get = (url, config) =>
  instance.get(url, config).then((r) => r.data)

export const post = (url, data, config) =>
  instance.post(url, data, config).then((r) => r.data)

export const put = (url, data, config) =>
  instance.put(url, data, config).then((r) => r.data)

export const del = (url, config) =>
  instance.delete(url, config).then((r) => r.data)

export default instance
