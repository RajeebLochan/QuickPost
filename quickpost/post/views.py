from django.shortcuts import redirect, render
from .models import Post , Comment
from .forms import PostForm, UserRegistrationForm
from django.contrib.auth.decorators import login_required 
from django.contrib.auth import login, authenticate
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
import datetime
from django.core.cache import cache
# @login_required
# Create your views here.
def index(request):
    return render(request,'index.html')


#post list view
# @login_required
def post_list(request):
    # Add daily quote logic
    quotes_cached = cache.get("daily_quote")
    if not quotes_cached:
        quotes_cached = get_daily_quote()
        cache.set("daily_quote", quotes_cached, timeout=24*3600)  # 24 hours
    
    posts = Post.objects.all().order_by('-created_at')
    return render(request, 'post_list.html', {'posts': posts, 'daily_quote': quotes_cached})

#create post view
@login_required
def create_post(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            return redirect('post_list')
    else:
        form = PostForm()
    return render(request, 'create_post.html', {'form': form})

#edit post view
@login_required
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            return redirect('post_list')
    else:
        form = PostForm(instance=post)
    return render(request, 'create_post.html', {'form': form, 'post': post})

#post delete view
@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    if request.method == 'POST':
        post.delete()
        return redirect('post_list')
    return render(request, 'delete_post.html', {'post': post})


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])
            user.save()
            login(request, user)
            return redirect('login')
            
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


def home(request):
    return render(request, 'index.html')


# def profile(request):
#     if request.user.is_authenticated:

#         posts = Post.objects.filter(user=request.user).order_by('-created_at')
#         return render(request, 'profile.html', {'posts': posts})
#     else:
#         return redirect('login')
@login_required
def profile(request, username):
    user = get_object_or_404(User, username=username)
    posts = Post.objects.filter(user=user).order_by('-created_at')
    
    context = {
        'profile_user': user,
        'posts': posts,
    }
    return render(request, 'profile.html', context)

@login_required
def like_post(request, post_id):
    if request.method == "POST":
        post = Post.objects.get(id=post_id)
        liked = False

        if request.user in post.likes.all():
            post.likes.remove(request.user)
        else:
            post.likes.add(request.user)
            liked = True

        return JsonResponse({
            "liked": liked,
            "likes_count": post.likes.count()
        })

    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def dislike_post(request, post_id):
    if request.method == "POST":
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return JsonResponse({"error": "Post not found"}, status=404)

        disliked = False

        if request.user in post.dislikes.all():
            post.dislikes.remove(request.user)
        else:
            post.dislikes.add(request.user)
            disliked = True
            # Remove like if it exists
            if request.user in post.likes.all():
                post.likes.remove(request.user)

        return JsonResponse({
            "disliked": disliked,
            "dislikes_count": post.dislikes.count(),
            "likes_count": post.likes.count()
        })

    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def add_comment(request, post_id):
    if request.method == "POST":
        post = Post.objects.get(id=post_id)
        content = request.POST.get("content")
        if content.strip():
            comment = Comment.objects.create(
                post=post,
                user=request.user,
                content=content
            )
            return JsonResponse({
                "success": True,
                "comment_user": comment.user.username,
                "comment_content": comment.content,
                "comment_time": comment.created_at.strftime("%b %d, %Y %H:%M"),
                "comments_count": post.comments.count()
            })
    return JsonResponse({"success": False})

QUOTES = [
    ("Do small things with great love.", "Mother Teresa"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("In the middle of every difficulty lies opportunity.", "Albert Einstein"),
    ("What we think, we become.", "Buddha"),
    ("Happiness is not something ready made. It comes from your own actions.", "Dalai Lama"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Life is what happens when you're busy making other plans.", "John Lennon"),
    ("You must be the change you wish to see in the world.", "Mahatma Gandhi"),
    ("Believe you can and you're halfway there.", "Theodore Roosevelt"),
    ("Act as if what you do makes a difference. It does.", "William James"),
    ("Success is not final, failure is not fatal: It is the courage to continue that counts.", "Winston Churchill"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("Everything you’ve ever wanted is on the other side of fear.", "George Addair"),
    ("The only limit to our realization of tomorrow will be our doubts of today.", "Franklin D. Roosevelt"),
    ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
    ("Do what you can, with what you have, where you are.", "Theodore Roosevelt"),
    ("You are never too old to set another goal or to dream a new dream.", "C.S. Lewis"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("Keep your face always toward the sunshine—and shadows will fall behind you.", "Walt Whitman"),
]

def get_daily_quote():
    # deterministic by date so all users see the same quote for the day
    today = datetime.date.today()
    if not QUOTES:
        return {"text": "", "author": "", "date": today}
    index = today.toordinal() % len(QUOTES)
    return {"text": QUOTES[index][0], "author": QUOTES[index][1], "date": today}


