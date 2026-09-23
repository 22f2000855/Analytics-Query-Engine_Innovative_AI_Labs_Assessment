import { useState, useCallback } from 'react'
import { postQuery } from '../api/client'

export function useQuery() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const submit = useCallback(async (question) => {
    setLoading(true)
    setError(null)
    try {
      const data = await postQuery(question)
      setResult(data)
      return data
    } catch (e) {
      setError(e.message)
      setResult(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { loading, error, result, submit }
}
