from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def dashboard_view(request):
    from medicines.models import Medicine
    total_medicines = Medicine.objects.count()
    return render(request, 'dashboard.html', {'total_medicines': total_medicines})

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')
