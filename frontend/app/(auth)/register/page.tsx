'use client'

import { useState } from 'react'
import { useRegister } from '@/lib/queries/use-auth'
import { Button } from '@/components/ui/button'
import { InputField } from '@/components/common/form-field'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Link from 'next/link'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [phone, setPhone] = useState('')
  const register = useRegister()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    register.mutate({
      email,
      password,
      company_name: companyName,
      phone: phone || undefined,
    })
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Create Account</CardTitle>
          <CardDescription>Register your landscaping company</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <InputField
              label="Company Name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              required
              disabled={register.isPending}
            />
            <InputField
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={register.isPending}
            />
            <InputField
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={register.isPending}
            />
            <InputField
              label="Phone (Optional)"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={register.isPending}
            />
            <Button type="submit" className="w-full" disabled={register.isPending}>
              {register.isPending ? 'Creating account...' : 'Create Account'}
            </Button>
            <div className="text-center text-sm text-muted-foreground">
              Already have an account?{' '}
              <Link href="/login" className="text-primary hover:underline">
                Sign in
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

